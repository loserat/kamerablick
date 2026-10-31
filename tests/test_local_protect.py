import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import ssl
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1] / 'app'))
from protect import Protect, ProtectError, certificate_fingerprint, connection_credentials
from local_protect import _sessions


class LocalNvr(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        root = Path(cls.temp.name)
        subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-keyout',str(root/'key.pem'),'-out',str(root/'cert.pem'),'-days','1','-subj','/CN=localhost'], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def handle(self):
                try: super().handle()
                except (ConnectionResetError, BrokenPipeError): pass
            def reply(self, value, status=200, headers=None):
                raw = value if isinstance(value,bytes) else json.dumps(value).encode()
                self.send_response(status)
                for key, val in (headers or {}).items(): self.send_header(key,val)
                self.send_header('Content-Length',str(len(raw)))
                self.end_headers();self.wfile.write(raw)
            def do_POST(self):
                body=json.loads(self.rfile.read(int(self.headers.get('Content-Length',0))))
                cls.requests.append(('POST',self.path,body))
                if cls.redirect: return self.reply({},302,{'Location':'https://example.invalid/'})
                if body.get('username')!='tester' or body.get('password')!='local-secret':
                    return self.reply({'error':'invalid'},401)
                cls.logins += 1
                headers={'X-CSRF-Token':'csrf-for-test'}
                if cls.issue_cookie: headers['Set-Cookie']=cls.cookie+'=session-for-test; Path=/; HttpOnly; Secure; Partitioned'
                self.reply({},headers=headers)
            def do_GET(self):
                cls.requests.append(('GET',self.path,dict(self.headers)))
                if cls.reject_once:
                    cls.reject_once=False
                    return self.reply({},401)
                if '/integration/' in self.path:
                    if self.headers.get('X-API-Key')!='integration-test-key': return self.reply({},401)
                elif self.headers.get('Cookie')!=cls.cookie+'=session-for-test': return self.reply({},401)
                if self.path.endswith('/bootstrap'): return self.reply({'cameras':[cls.camera]})
                if self.path.endswith('/cameras'): return self.reply([cls.camera])
                if '/snapshot' in self.path: return self.reply(b'\xff\xd8test-jpeg')
                if self.path.endswith('/rtsps-stream'): return self.reply({'medium':'rtsps://127.0.0.1:7441/public-alias'})
                if '/cameras/camera-1' in self.path: return self.reply(cls.camera)
                return self.reply({},404)
        cls.http=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.load_cert_chain(root/'cert.pem',root/'key.pem')
        cls.http.socket=context.wrap_socket(cls.http.socket,server_side=True)
        cls.host='https://127.0.0.1:'+str(cls.http.server_port)
        threading.Thread(target=cls.http.serve_forever,daemon=True).start()
        cls.pin=certificate_fingerprint(cls.host)

    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown();cls.http.server_close();cls.temp.cleanup()

    def setUp(self):
        _sessions.clear()
        type(self).requests=[];type(self).logins=0;type(self).issue_cookie=True
        type(self).redirect=False;type(self).reject_once=False;type(self).cookie='TOKEN'
        type(self).camera={'id':'camera-1','name':'Testkamera','type':'G5','state':'CONNECTED',
            'channels':[{'id':1,'isRtspEnabled':True,'rtspAlias':'test-alias'}]}
        self.credentials={'host':self.host,'auth_mode':'local','username':'tester','password':'local-secret','fingerprint':self.pin}

    def test_tls_challenge_and_changed_pin_never_send_password(self):
        for fingerprint in ('','0'*64):
            _sessions.clear()
            with self.assertRaises(ProtectError) as caught:
                Protect(self.credentials|{'fingerprint':fingerprint}).cameras()
            self.assertEqual(caught.exception.code,409)
        self.assertEqual(self.requests,[])

    def test_login_cookie_camera_snapshot_and_stream_without_key(self):
        client=Protect(self.credentials)
        self.assertEqual(client.cameras()[0]['name'],'Testkamera')
        self.assertTrue(client.snapshot('camera-1').startswith(b'\xff\xd8'))
        self.assertEqual(client.streams('camera-1','medium'),'rtsps://127.0.0.1:7441/test-alias?enableSrtp')
        self.assertEqual(self.logins,1)
        self.assertEqual(self.requests[0][2]['rememberMe'],False)
        get_headers=next(row[2] for row in self.requests if row[0]=='GET')
        self.assertEqual(get_headers['X-CSRF-Token'],'csrf-for-test')
        self.assertNotIn('password',get_headers)

    def test_session_cache_is_shared_but_new_password_is_never_reused(self):
        Protect(self.credentials).cameras();Protect(dict(self.credentials)).cameras()
        self.assertEqual(self.logins,1)
        with self.assertRaises(ProtectError):
            Protect(self.credentials|{'password':'changed-secret'}).cameras()
        self.assertEqual(len([r for r in self.requests if r[0]=='POST']),2)

    def test_expired_session_reauthenticates_once(self):
        client=Protect(self.credentials);client.cameras();type(self).reject_once=True
        client.camera('camera-1')
        self.assertEqual(self.logins,2)

    def test_wrong_password_is_rate_limited(self):
        bad=self.credentials|{'password':'wrong'}
        for expected in (401,429):
            with self.assertRaises(ProtectError) as caught: Protect(bad).cameras()
            self.assertEqual(caught.exception.code,expected)
        self.assertEqual(len(self.requests),1)

    def test_missing_session_and_redirect_are_rejected(self):
        type(self).issue_cookie=False
        with self.assertRaises(ProtectError): Protect(self.credentials).cameras()
        _sessions.clear();type(self).redirect=True
        with self.assertRaises(ProtectError): Protect(self.credentials).cameras()
        self.assertEqual(len(self.requests),2)

    def test_uos_cookie_is_supported(self):
        type(self).cookie='UOS_TOKEN'
        self.assertEqual(len(Protect(self.credentials).cameras()),1)

    def test_optional_key_uses_public_streams_and_events(self):
        client=Protect(self.credentials|{'api_key':'integration-test-key'})
        self.assertEqual(len(client.cameras()),1)
        self.assertEqual(client.streams('camera-1','medium'),'rtsps://127.0.0.1:7441/public-alias')
        with patch.object(client.integration,'event_socket',return_value='events'):
            self.assertEqual(client.event_socket(),'events')
        self.assertEqual(self.logins,1)

    def test_no_key_never_changes_stream_settings_and_explains_events(self):
        type(self).camera={**self.camera,'channels':[]}
        client=Protect(self.credentials)
        with self.assertRaises(ProtectError) as caught: client.streams('camera-1','medium',True)
        self.assertTrue(caught.exception.details['needs_api_key'])
        self.assertEqual([r[1] for r in self.requests if r[0]=='POST'],['/api/auth/login'])
        with self.assertRaises(ProtectError) as caught: client.event_socket()
        self.assertEqual(caught.exception.code,404)

    def test_validation_and_no_secret_reuse_across_host_user_or_mode(self):
        for change in ({'username':''},{'password':''},{'password':True},{'fingerprint':'bad'}):
            with self.assertRaises(ProtectError): Protect(self.credentials|change)
        base={'host':self.host,'auth_mode':'local','username':'tester'}
        self.assertEqual(connection_credentials(base,self.credentials)['password'],'local-secret')
        self.assertEqual(connection_credentials(base|{'username':'other'},self.credentials)['password'],'')
        self.assertEqual(connection_credentials(base|{'username':'other'},self.credentials|{'api_key':'private-key'})['api_key'],'')
        self.assertEqual(connection_credentials(base|{'host':'192.0.2.20'},self.credentials)['password'],'')
        result=connection_credentials({'host':self.host,'auth_mode':'api_key'},self.credentials)
        self.assertNotIn('password',result)
        with self.assertRaises(ProtectError): connection_credentials(base|{'password':False},self.credentials)
