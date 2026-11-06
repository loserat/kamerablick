import http.client, importlib.util, json, os, ssl, subprocess, sys, tempfile, threading, time, unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
sys.path.insert(0,str(Path(__file__).parents[1]/'app'))
sys.path.insert(0,str(Path(__file__).parents[1]/'pi'))
import server
from protect import Protect,ProtectError,normalize_host,certificate_fingerprint
spec=importlib.util.spec_from_file_location('pi_agent',Path(__file__).parents[1]/'pi/agent.py')
pi=importlib.util.module_from_spec(spec);spec.loader.exec_module(pi)

class ApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.http=ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
        cls.port=cls.http.server_port
        threading.Thread(target=cls.http.serve_forever,daemon=True).start()
    @classmethod
    def tearDownClass(cls): cls.http.shutdown();cls.http.server_close()
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();server.DATA=Path(self.tmp.name)
        server.PASSWORD='test-only';server.DEMO=True;server.sessions.clear();server.failures.clear()
        server.state.update(active=False,tv='Wiedergabe aus',deadline=0)
        self.token=self.call('/api/login',{'password':'test-only'})[1]['token']
    def tearDown(self): self.tmp.cleanup()
    def call(self,path,body=None,token=None):
        conn=http.client.HTTPConnection('127.0.0.1',self.port,timeout=5)
        conn.request('POST' if body is not None else 'GET',path,body=json.dumps(body) if body is not None else None,
                     headers={'Authorization':'Bearer '+(token if token is not None else getattr(self,'token','')),'Content-Type':'application/json'})
        r=conn.getresponse();status=r.status;raw=r.read();conn.close()
        return status,json.loads(raw)
    def test_brand_assets_are_public_and_private_files_stay_unavailable(self):
        for path,kind,signature in (
            ('/icon.svg','image/svg+xml',b'<svg'),
            ('/icon-512.png','image/png',b'\x89PNG\r\n\x1a\n'),
            ('/apple-touch-icon.png','image/png',b'\x89PNG\r\n\x1a\n'),
        ):
            with self.subTest(path=path):
                conn=http.client.HTTPConnection('127.0.0.1',self.port,timeout=5)
                conn.request('GET',path)
                response=conn.getresponse()
                self.assertEqual(response.status,200)
                self.assertEqual(response.getheader('Content-Type'),kind)
                self.assertEqual(response.getheader('X-Content-Type-Options'),'nosniff')
                self.assertTrue(response.read().startswith(signature))
                conn.close()
        for path in ('/.env','/../.env','/icon.svg/../../.env','/docs/INSTALLATION.md'):
            self.assertEqual(self.call(path,token='invalid')[0],404)
    def test_auth_logout_and_rate_limit(self):
        self.assertEqual(self.call('/api/status',token='invalid')[0],401)
        self.assertEqual(self.call('/api/logout',{})[0],200)
        self.assertEqual(self.call('/api/status')[0],401)
        for _ in range(8): self.assertEqual(self.call('/api/login',{'password':'wrong'})[0],401)
        self.assertEqual(self.call('/api/login',{'password':'wrong'})[0],429)
    def test_overview_snapshot_requires_admin_and_uses_only_saved_camera(self):
        self.assertEqual(self.call('/api/protect/preview',{},token='invalid')[0],401)
        self.assertEqual(self.call('/api/protect/preview',{})[0],400)
        server.save('config.json',server.DEFAULT|{'camera_source':'protect','camera_id':'saved-camera'})
        server.save('protect.json',{'host':'https://console.invalid','api_key':'private-test-key'})
        self.assertEqual(self.call('/api/protect/preview',{'camera_id':'other-camera'})[0],400)
        with patch.object(server,'Protect') as protect:
            protect.return_value.snapshot.return_value=b'\xff\xd8test-jpeg'
            conn=http.client.HTTPConnection('127.0.0.1',self.port,timeout=5)
            conn.request('POST','/api/protect/preview',body='{}',headers={'Authorization':'Bearer '+self.token,'Content-Type':'application/json'})
            response=conn.getresponse()
            self.assertEqual(response.status,200)
            self.assertEqual(response.getheader('Content-Type'),'image/jpeg')
            self.assertEqual(response.getheader('Cache-Control'),'no-store')
            self.assertEqual(response.read(),b'\xff\xd8test-jpeg')
            conn.close()
            protect.return_value.snapshot.assert_called_once_with('saved-camera')
            self.assertEqual(protect.call_args.args[0]['api_key'],'private-test-key')
        self.assertEqual(self.call('/api/protect/preview',{},token='invalid')[0],401)
    def test_cec_receiver_is_separate_from_admin_and_tv_access(self):
        with patch.object(server,'TOKEN','host-key-'+'a'*32):
            code,local=self.call('/api/tv/provision',{},'host-key-'+'a'*32)
        self.assertEqual(code,200)
        paired=self.call('/api/tv/pair',{})[1]
        self.assertNotIn('receiver',paired)
        self.assertNotEqual(local['token'],local['receiver'])
        for credential in (self.token,local['token'],'invalid'):
            self.assertEqual(self.call('/api/tv/input',{'client':'a'*24},credential)[0],401)
        server.DEMO=False
        with patch.object(server,'agent',return_value={'boot':'pi','cursor':2,'events':[{'id':2,'key':'Enter'}]}) as hardware:
            code,data=self.call('/api/tv/input',{'client':'a'*24,'cursor':1,'boot':'pi'},local['receiver'])
            self.assertEqual(code,200);self.assertEqual(data['events'][0]['key'],'Enter')
            hardware.assert_called_once_with('remote_poll',remote_input={'client':'a'*24,'cursor':1,'boot':'pi'})
        self.assertEqual(self.call('/api/config',{},local['receiver'])[0],401)
        self.assertEqual(self.call('/api/tv/action',{'action':'off'},local['receiver'])[0],401)
        self.assertEqual((server.DATA/'tv-receiver.json').stat().st_mode&0o777,0o600)
        self.call('/api/tv/revoke',{})
        self.assertEqual(self.call('/api/tv/input',{'client':'a'*24},local['receiver'])[0],401)
    def test_config_validation_and_secret_redaction(self):
        status,_=self.call('/api/config',{'stream_url':'rtsps://example/secret','gpio_pin':17,'auto_off_minutes':7})
        self.assertEqual(status,200)
        data=self.call('/api/status')[1]
        self.assertTrue(data['config']['has_stream']);self.assertNotIn('secret',json.dumps(data))
        for invalid in (99,-1,True,2.5,'garbage'):
            self.assertEqual(self.call('/api/config',{'gpio_pin':invalid})[0],400)
        self.assertEqual(server.config()['gpio_pin'],17)
        self.assertEqual(os.stat(server.DATA/'config.json').st_mode&0o777,0o600)
    def test_multiple_manual_cameras_are_retained_and_tv_can_only_choose_saved_entries(self):
        first={'camera_name':'Haustür','stream_url':'rtsps://camera.invalid/private-one'}
        second={'camera_name':'Garten','stream_url':'rtsps://camera.invalid/private-two'}
        self.assertEqual(self.call('/api/config',first)[0],200)
        self.assertEqual(self.call('/api/config',second)[0],200)
        self.assertEqual(self.call('/api/cameras',token='invalid')[0],401)
        access=self.call('/api/tv/pair',{})[1]['token']
        code,data=self.call('/api/tv/status',token=access)
        self.assertEqual(code,200)
        self.assertEqual([r['name'] for r in data['cameras']],['Haustür','Garten'])
        self.assertNotIn('private-',json.dumps(data))
        self.assertNotIn('stream_url',json.dumps(data))
        key=data['cameras'][0]['id']
        self.assertEqual(self.call('/api/tv/action',{'action':'on','camera_id':key},access)[0],200)
        self.assertEqual(server.config()['stream_url'],first['stream_url'])
        self.assertEqual(self.call('/api/tv/action',{'action':'on','camera_id':'manual:invented'},access)[0],400)
        self.assertEqual(self.call('/api/tv/action',{'action':'on','camera_id':key,'gpio_pin':2},access)[0],400)
        self.assertEqual(self.call('/api/cameras/remove',{'camera_id':key},access)[0],401)
        self.assertEqual((server.DATA/'manual-cameras.json').stat().st_mode&0o777,0o600)
    def test_home_test_does_not_invent_cameras_before_connecting_a_real_source(self):
        access=self.call('/api/tv/pair',{})[1]['token']
        with patch.object(server,'HOME_TEST',True):
            self.assertEqual(self.call('/api/tv/status',token=access)[1]['cameras'],[])
    def test_legacy_manual_camera_is_not_lost_when_adding_another_camera(self):
        server.save('config.json',server.DEFAULT|{'camera_name':'Bisherige Kamera','stream_url':'rtsps://private/legacy'})
        self.assertEqual(self.call('/api/config',{'camera_name':'Garten','stream_url':'rtsps://private/garden'})[0],200)
        data=self.call('/api/cameras')[1]
        self.assertEqual([r['name'] for r in data['cameras']],['Bisherige Kamera','Garten'])
        self.assertEqual(self.call('/api/cameras/select',{'camera_id':data['cameras'][0]['id']})[0],200)
        self.assertEqual(server.config()['stream_url'],'rtsps://private/legacy')
    def test_manual_library_write_failure_restores_previous_configuration(self):
        self.call('/api/config',{'camera_name':'Haustür','stream_url':'rtsps://private/one'})
        previous=server.config();stored=server.read('manual-cameras.json',[]);write=server.save
        def fail_library(name,value):
            if name=='manual-cameras.json':raise OSError('disk unavailable')
            return write(name,value)
        with patch.object(server,'save',side_effect=fail_library):
            self.assertEqual(self.call('/api/config',{'camera_name':'Garten','stream_url':'rtsps://private/two'})[0],502)
        self.assertEqual(server.config(),previous)
        self.assertEqual(server.read('manual-cameras.json',[]),stored)
    def test_protect_tv_switch_preserves_settings_and_rejects_offline_or_unknown_cameras(self):
        server.DEMO=False
        previous=server.DEFAULT|{'camera_source':'protect','camera_id':'one','stream_url':'rtsps://private/one','gpio_pin':21,'auto_off_minutes':15}
        server.save('config.json',previous)
        cred={'host':'https://private-console.invalid','api_key':'private-test-key'}
        server.save('protect.json',cred)
        access=self.call('/api/tv/pair',{})[1]['token']
        rows=[{'id':'one','name':'Haustür','state':'CONNECTED'},
              {'id':'two','name':'Garten','state':'CONNECTED'},
              {'id':'three','name':'Garage','state':'DISCONNECTED'}]
        with patch.object(server,'Protect') as factory,patch.object(server,'agent',return_value={'active':False}),patch.object(server,'maintenance_status',return_value={'job':None}):
            factory.return_value.cameras.return_value=rows
            factory.return_value.streams.return_value='rtsps://private/two'
            code,data=self.call('/api/tv/status',token=access)
            self.assertEqual(code,200)
            self.assertEqual(len(data['cameras']),3)
            self.call('/api/tv/status',token=access)
            factory.return_value.cameras.assert_called_once()
            for secret in ('private-console','private-test-key','rtsps://'):
                self.assertNotIn(secret,json.dumps(data))
            self.assertEqual(self.call('/api/tv/action',{'action':'on','camera_id':'protect:two'},access)[0],200)
            factory.return_value.streams.assert_called_once_with('two','medium')
            updated=server.config()
            self.assertEqual(updated['camera_id'],'two')
            self.assertEqual(updated['gpio_pin'],21)
            self.assertEqual(updated['auto_off_minutes'],15)
            self.assertEqual(server.credentials(),cred)
            for key in ('protect:three','protect:invented'):
                self.assertEqual(self.call('/api/tv/action',{'action':'on','camera_id':key},access)[0],400)
                self.assertEqual(server.config(),updated)
    def test_only_admin_can_enable_a_missing_protect_stream(self):
        server.save('protect.json',{'host':'https://private.invalid','api_key':'private-key'})
        access=self.call('/api/tv/pair',{})[1]['token']
        with patch.object(server,'Protect') as factory:
            factory.return_value.cameras.return_value=[{'id':'two','name':'Garten','state':'CONNECTED'}]
            factory.return_value.streams.return_value='rtsps://private/two'
            self.assertEqual(self.call('/api/tv/action',{'action':'on','camera_id':'protect:two','enable_stream':True},access)[0],400)
            factory.return_value.streams.assert_not_called()
            self.assertEqual(self.call('/api/cameras/select',{'camera_id':'protect:two','enable_stream':True})[0],200)
            factory.return_value.streams.assert_called_once_with('two','medium',enable=True)
    def test_tv_camera_failure_keeps_working_camera_and_hides_protect_details(self):
        server.DEMO=False
        previous=server.DEFAULT|{'camera_source':'protect','camera_id':'one','stream_url':'rtsps://secret/one'}
        server.save('config.json',previous)
        server.save('protect.json',{'host':'https://private.invalid','api_key':'private-key'})
        access=self.call('/api/tv/pair',{})[1]['token']
        with patch.object(server,'Protect') as factory,patch.object(server,'maintenance_status',return_value={'job':None}):
            factory.return_value.cameras.return_value=[{'id':'two','name':'Garten','state':'CONNECTED'}]
            factory.return_value.streams.side_effect=ProtectError('private internal error',409,host='private-host',fingerprint='private-pin')
            code,data=self.call('/api/tv/action',{'action':'on','camera_id':'protect:two'},access)
        self.assertEqual(code,400)
        self.assertNotIn('private',json.dumps(data))
        self.assertEqual(server.config(),previous)
    def test_camera_removal_and_switching_are_admin_only_and_blocked_during_updates(self):
        self.call('/api/config',{'camera_name':'Haustür','stream_url':'rtsps://private/one'})
        self.call('/api/config',{'camera_name':'Garten','stream_url':'rtsps://private/two'})
        rows=self.call('/api/cameras')[1]['cameras'];first,second=[r['id'] for r in rows]
        self.assertEqual(self.call('/api/cameras/remove',{'camera_id':second})[0],400)
        self.assertEqual(self.call('/api/cameras/select',{'camera_id':first})[0],200)
        self.assertEqual(self.call('/api/cameras/remove',{'camera_id':second})[0],200)
        self.assertEqual(len(self.call('/api/cameras')[1]['cameras']),1)
        access=self.call('/api/tv/pair',{})[1]['token']
        server.DEMO=False
        with patch.object(server,'maintenance_status',return_value={'job':{'busy':True}}):
            self.assertEqual(self.call('/api/cameras/select',{'camera_id':first})[0],409)
            self.assertEqual(self.call('/api/tv/action',{'action':'on','camera_id':first},access)[0],409)
    def test_demo_selection_and_countdown(self):
        self.assertEqual(self.call('/api/protect/connect',{'demo':True})[0],200)
        self.assertEqual(self.call('/api/protect/select',{'camera_id':'not-found'})[0],400)
        self.assertEqual(self.call('/api/protect/select',{'camera_id':'demo-garage'})[0],400)
        self.assertEqual(self.call('/api/protect/select',{'camera_id':'demo-entry','quality':'medium'})[0],200)
        self.assertEqual(server.config()['camera_source'],'demo')
        self.assertEqual(self.call('/api/action',{'action':'on'})[0],200)
        self.assertTrue(self.call('/api/status')[1]['state']['active'])
        server.state['deadline']=time.monotonic()-1
        self.assertFalse(self.call('/api/status')[1]['state']['active'])
    def test_protect_discovery_stream_repair_and_credentials(self):
        cameras=[{'id':'camera-1','name':'Haustür','model':'G6','state':'CONNECTED'}]
        with patch.object(server,'Protect') as client:
            client.return_value.cameras.return_value=cameras
            code,data=self.call('/api/protect/connect',{'host':'192.168.1.20','api_key':'sensitive-key'})
            self.assertEqual(code,200);self.assertNotIn('sensitive-key',json.dumps(data))
            self.assertEqual(server.credentials(),{}) # No partial setup save.
            client.return_value.streams.side_effect=ProtectError('Kein Stream',409,needs_stream=True)
            code,data=self.call('/api/protect/select',{'camera_id':'camera-1','quality':'medium'})
            self.assertEqual(code,409);self.assertTrue(data['needs_stream'])
            client.return_value.streams.side_effect=None;client.return_value.streams.return_value='rtsps://192.168.1.20/stream-secret'
            self.assertEqual(self.call('/api/protect/select',{'camera_id':'camera-1','quality':'medium','enable_stream':True})[0],200)
            client.return_value.streams.assert_called_with('camera-1','medium',True)
            self.assertEqual(server.credentials()['api_key'],'sensitive-key')
            code,data=self.call('/api/status');self.assertNotIn('sensitive-key',json.dumps(data));self.assertNotIn('stream-secret',json.dumps(data))
            self.assertEqual(server.config()['camera_source'],'protect')
    def test_failed_agent_preserves_config(self):
        server.DEMO=False
        with patch.object(server,'agent',side_effect=ValueError('offline')):
            self.assertEqual(self.call('/api/config',{'gpio_pin':18})[0],400)
        self.assertEqual(server.config()['gpio_pin'],17)
    def test_local_nvr_setup_keeps_secrets_private_and_tests_connection_in_ui(self):
        cameras=[{'id':'local-1','name':'Testkamera','model':'G5','state':'CONNECTED'}]
        with patch.object(server,'Protect') as client:
            client.return_value.cameras.return_value=cameras
            client.return_value.streams.return_value='rtsps://192.0.2.20/private-alias'
            client.return_value.snapshot.return_value=b'\xff\xd8image'
            body={'host':'192.0.2.20','auth_mode':'local','username':'local-user','password':'local-private-password'}
            code,result=self.call('/api/protect/connect',body)
            self.assertEqual(code,200);self.assertNotIn('password',json.dumps(result))
            self.assertEqual(server.credentials(),{})
            self.assertEqual(self.call('/api/protect/select',{'camera_id':'local-1','quality':'medium'})[0],200)
            self.assertEqual(server.credentials()['password'],'local-private-password')
            status=self.call('/api/status')[1]
            self.assertEqual(status['protect']['auth_mode'],'local')
            self.assertTrue(status['protect']['has_password'])
            self.assertNotIn('local-private-password',json.dumps(status))
            self.assertNotIn('private-alias',json.dumps(status))
            self.assertEqual((server.DATA/'protect.json').stat().st_mode&0o777,0o600)
            self.assertEqual(self.call('/api/protect/test',{},token='invalid')[0],401)
            code,result=self.call('/api/protect/test',{})
            self.assertEqual(code,200);self.assertTrue(result['snapshot_ok'])
            self.assertFalse(result['hardware_tested'])
            self.assertNotIn('private-alias',json.dumps(result))
            self.assertEqual(self.call('/api/protect/connect',body|{'password':''})[0],200)
            self.assertEqual(client.call_args.args[0]['password'],'local-private-password')
    def test_no_saved_key_reuse_for_different_host(self):
        server.save('protect.json',{'host':'https://192.168.1.20','api_key':'sensitive-key'})
        code,_=self.call('/api/protect/connect',{'host':'192.168.1.21'})
        self.assertEqual(code,400)
    def test_tv_access_is_limited_and_revocable(self):
        self.assertEqual(self.call('/api/tv/pair',{},token='invalid')[0],401)
        self.assertEqual(self.call('/api/tv/status',token='invalid')[0],401)
        access=self.call('/api/tv/pair',{})[1]['token']
        self.assertEqual(self.call('/api/tv/pair',{})[1]['token'],access)
        self.assertEqual(os.stat(server.DATA/'tv-access.json').st_mode&0o777,0o600)
        server.save('protect.json',{'api_key':'private-protect-key'})
        server.save('config.json',server.DEFAULT|{'stream_url':'rtsps://host/private-stream','camera_name':'Haustür'})
        code,data=self.call('/api/tv/status',token=access)
        self.assertEqual(code,200);self.assertEqual(data['camera_name'],'Haustür')
        self.assertNotIn('private',json.dumps(data));self.assertNotIn('config',data)
        self.assertEqual(self.call('/api/status',token=access)[0],401)
        self.assertEqual(self.call('/api/config',{'gpio_pin':18},token=access)[0],401)
        self.assertEqual(self.call('/api/tv/pair',{},token=access)[0],401)
        self.assertEqual(self.call('/api/tv/action',{'action':'configure'},token=access)[0],400)
        self.assertEqual(self.call('/api/tv/action',{'action':'on'},token=access)[0],200)
        self.assertTrue(self.call('/api/tv/status',token=access)[1]['active'])
        self.assertEqual(self.call('/api/tv/action',{'action':'menu'},token=access)[0],200)
        self.assertFalse(self.call('/api/tv/status',token=access)[1]['active'])
        self.assertEqual(self.call('/api/tv/revoke',{})[0],200)
        self.assertEqual(self.call('/api/tv/status',token=access)[0],401)
    def test_only_local_trusted_launcher_can_provision(self):
        with patch.object(server,'TOKEN','p'*32):
            self.assertEqual(self.call('/api/tv/provision',{},token='')[0],401)
            self.assertEqual(self.call('/api/tv/provision',{},token=self.token)[0],401)
            access=self.call('/api/tv/provision',{},token='p'*32)[1]['token']
            self.assertEqual(self.call('/api/tv/status',token=access)[0],200)
            self.assertEqual(self.call('/api/config',{'gpio_pin':18},token=access)[0],401)
    def test_tv_countdown_without_dashboard_poll(self):
        access=self.call('/api/tv/pair',{})[1]['token']
        self.call('/api/tv/action',{'action':'on'},token=access)
        server.state['deadline']=time.monotonic()-1
        self.assertFalse(self.call('/api/tv/status',token=access)[1]['active'])
    def test_tv_real_action_uses_hardware_service(self):
        access=self.call('/api/tv/pair',{})[1]['token'];server.DEMO=False
        with patch.object(server,'agent',return_value={'message':'menu'}) as hardware:
            self.assertEqual(self.call('/api/tv/action',{'action':'menu'},token=access)[0],200)
            hardware.assert_called_once_with('menu')
        server.save('config.json',server.DEFAULT|{'camera_source':'demo'})
        with patch.object(server,'agent') as hardware:
            self.assertEqual(self.call('/api/tv/action',{'action':'on'},token=access)[0],400)
            hardware.assert_not_called()
    def test_health(self): self.assertEqual(self.call('/healthz')[1],{'ok':True})
    def test_browser_update_requires_admin_confirmation_and_real_pi_mode(self):
        body={'version':'v1.0.1','confirm':True}
        self.assertEqual(self.call('/api/update/install',body,token='invalid')[0],401)
        self.assertEqual(self.call('/api/update/install',body)[0],400)
        server.DEMO=False
        support={'available':True,'persistent':True,'job':None}
        with patch.object(server,'maintenance_status',return_value=support),patch.object(server,'maintenance_request',return_value={'job':{'phase':'queued'},'watch':'w'*43}) as host:
            self.assertEqual(self.call('/api/update/install',body|{'confirm':False})[0],400)
            self.assertEqual(self.call('/api/update/install',body|{'command':'touch /tmp/x'})[0],400)
            self.assertEqual(self.call('/api/update/install',body|{'version':'latest'})[0],400)
            self.assertEqual(self.call('/api/update/install',body)[0],202)
            host.assert_called_once_with('update',{'version':'v1.0.1'})
    def test_release_source_is_fixed_and_progress_capability_is_read_only(self):
        server.DEMO=False
        info={'version':'v1.0.1','notes':'test release'}
        support={'available':True,'persistent':True,'job':None}
        with patch.dict(os.environ,{'APP_VERSION':'v1.0.0'}),patch.object(server.release_info,'release',return_value=info) as release,patch.object(server,'maintenance_status',return_value=support):
            server.save('config.json',server.DEFAULT|{'github_repo':'untrusted/other-project'})
            code,result=self.call('/api/update')
            self.assertEqual(code,200);self.assertTrue(result['can_install'])
            release.assert_called_once_with(refresh=True)
        with patch.object(server,'maintenance_request',return_value={'job':{'phase':'verifying'}}) as host:
            self.assertEqual(self.call('/api/update/progress',{'watch':'short'},token='invalid')[0],401)
            code,result=self.call('/api/update/progress',{'watch':'w'*43},token='invalid')
            self.assertEqual(code,200);self.assertEqual(result['job']['phase'],'verifying')
            host.assert_called_once_with('watch',{'watch':'w'*43})
            self.assertEqual(self.call('/api/config',{'gpio_pin':18},token='w'*43)[0],401)
    def test_configuration_writes_wait_for_a_running_update(self):
        server.DEMO=False
        with patch.object(server,'maintenance_status',return_value={'job':{'busy':True}}):
            self.assertEqual(self.call('/api/config',{'gpio_pin':18})[0],409)

class ProtectTLS(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();root=Path(cls.temp.name)
        subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-keyout',str(root/'key.pem'),'-out',str(root/'cert.pem'),'-days','1','-subj','/CN=localhost'],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        cls.received=[]
        received=cls.received
        class Handler(BaseHTTPRequestHandler):
            def handle(self):
                try: super().handle()
                except (ConnectionResetError, BrokenPipeError): pass  # Expected during certificate-only handshakes.
            def log_message(self,*args): pass
            def do_GET(self):
                received.append(self.headers.get('X-API-Key'))
                self.send_response(200);self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(b'[]')
        cls.http=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        ctx=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);ctx.load_cert_chain(root/'cert.pem',root/'key.pem')
        cls.http.socket=ctx.wrap_socket(cls.http.socket,server_side=True)
        cls.host='https://127.0.0.1:'+str(cls.http.server_port)
        threading.Thread(target=cls.http.serve_forever,daemon=True).start()
    @classmethod
    def tearDownClass(cls): cls.http.shutdown();cls.http.server_close();cls.temp.cleanup()
    def test_certificate_challenge_does_not_send_key(self):
        self.received.clear()
        with self.assertRaises(ProtectError) as error: Protect({'host':self.host,'api_key':'test-key'}).cameras()
        self.assertEqual(error.exception.code,409);self.assertIn('fingerprint',error.exception.details)
        self.assertEqual(self.received,[])
    def test_pinned_certificate_accepts_key(self):
        pin=certificate_fingerprint(self.host)
        self.assertEqual(Protect({'host':self.host,'api_key':'test-key','fingerprint':pin}).cameras(),[])
        self.assertEqual(self.received[-1],'test-key')
    def test_wrong_pin_never_sends_key(self):
        self.received.clear()
        with self.assertRaises(ProtectError): Protect({'host':self.host,'api_key':'test-key','fingerprint':'0'*64}).cameras()
        self.assertEqual(self.received,[])
    def test_invalid_addresses(self):
        for host in ('http://host','https://user:pass@host','https://host/path','https://host/?x=1','https://host:bad'):
            with self.assertRaises(ProtectError): normalize_host(host)

class HardwareLogic(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.c=pi.Controller(Path(self.tmp.name)/'config.json',MagicMock())
        self.c.settings={'gpio_pin':17,'auto_off_minutes':5,'stream_url':'rtsps://host/token'}
    def tearDown(self): self.tmp.cleanup()
    def test_toggle_off_while_stream_crashed(self):
        self.c.want_on=True;self.c.player=MagicMock();self.c.player.poll.return_value=1
        with patch.object(self.c,'cec') as cec:
            self.c.action('toggle');cec.assert_called_once_with('standby 0\n')
        self.assertFalse(self.c.want_on)
    def test_reconnect_and_deadline(self):
        self.c.want_on=True;self.c.player=None
        with patch.object(self.c,'start_player') as start:
            self.c.tick();self.assertEqual(start.call_count,1)
            self.c.tick();self.assertEqual(start.call_count,1)
        self.c.deadline=time.monotonic()-1
        with patch.object(self.c,'cec') as cec: self.c.tick();cec.assert_called_once()
        self.assertFalse(self.c.want_on)
    def test_failed_gpio_change_keeps_working_button(self):
        old=MagicMock();self.c.button=old;self.c.button_factory.side_effect=RuntimeError('pin busy')
        with self.assertRaises(RuntimeError): self.c.configure(self.c.settings|{'gpio_pin':18})
        old.close.assert_not_called();self.assertEqual(self.c.settings['gpio_pin'],17)
    def test_return_to_menu_does_not_switch_tv_off(self):
        self.c.want_on=True;self.c.deadline=time.monotonic()+300
        self.c.player=MagicMock();self.c.player.poll.return_value=None
        with patch.object(self.c,'cec') as cec:
            self.c.action('menu');cec.assert_not_called()
        self.assertFalse(self.c.want_on);self.assertEqual(self.c.deadline,0)
        self.assertIsNone(self.c.player)
    def test_player_back_key_returns_to_menu_without_retry(self):
        self.c.want_on=True;self.c.player=MagicMock();self.c.player.poll.return_value=42
        with patch.object(self.c,'cec') as cec,patch.object(self.c,'start_player') as start:
            self.c.tick();cec.assert_not_called();start.assert_not_called()
        self.assertFalse(self.c.want_on);self.assertIsNone(self.c.player)
    def test_cec_failure_does_not_claim_tv_standby(self):
        self.c.want_on=True
        with patch.object(self.c,'cec',side_effect=RuntimeError()):
            with self.assertRaises(RuntimeError): self.c.action('off')
        self.assertFalse(self.c.want_on);self.assertIn('fehlgeschlagen',self.c.message)

if __name__=='__main__': unittest.main()
