"""Actual TLS/WebSocket fixture, with the same local Integration API envelope."""
import base64
import hashlib
import http.client
import json
from pathlib import Path
import queue
import select
import ssl
import struct
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
sys.path.insert(0,str(Path(__file__).parents[1]/'app'))
from protect import Protect, ProtectError, certificate_fingerprint
from telemetry import Telemetry


def frame(opcode,data):
    data=data.encode() if isinstance(data,str) else data
    return bytes([0x80|opcode,len(data)])+data if len(data)<126 else bytes([0x80|opcode,126])+struct.pack('!H',len(data))+data


def exact(sock,n):
    data=b''
    while len(data)<n:
        part=sock.recv(n-len(data))
        if not part:raise EOFError()
        data+=part
    return data


def receive(sock):
    header=exact(sock,2);length=header[1]&127
    if length==126:length=struct.unpack('!H',exact(sock,2))[0]
    if length==127:raise ValueError('oversized test frame')
    mask=exact(sock,4) if header[1]&128 else None
    payload=exact(sock,length)
    if mask:payload=bytes(value^mask[i%4] for i,value in enumerate(payload))
    return header[0]&15,payload


def eventually(test,timeout=4):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        if test():return
        time.sleep(.02)
    raise AssertionError('Expected transport state did not occur')


class ConsoleTransport(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();root=Path(cls.temp.name)
        subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-keyout',str(root/'key.pem'),'-out',str(root/'cert.pem'),'-days','1','-subj','/CN=localhost'],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        cls.data={'requests':[],'connections':0,'pings':0,'mode':'normal','outgoing':queue.Queue()}
        owner=cls
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def handle(self):
                try:super().handle()
                except (OSError,EOFError):pass
            def do_GET(self):
                state=owner.data;state['requests'].append((self.path,self.headers.get('X-API-Key')))
                if self.path.endswith('/cameras/camera-1'):
                    self.send_response(200);self.end_headers();self.wfile.write(b'{"id":"camera-1","state":"CONNECTED","type":"G6","featureFlags":{"smartDetectTypes":["person","vehicle"]}}');return
                if state['mode'] in ('unsupported','denied','redirect'):
                    self.send_response({'unsupported':404,'denied':401,'redirect':302}[state['mode']])
                    if state['mode']=='redirect':self.send_header('Location',owner.host+'/stolen-key')
                    self.end_headers();return
                key=self.headers['Sec-WebSocket-Key']
                accept=base64.b64encode(hashlib.sha1((key+'258EAFA5-E914-47DA-95CA-C5AB0DC85B11').encode()).digest()).decode()
                self.send_response(101);self.send_header('Upgrade','websocket');self.send_header('Connection','Upgrade');self.send_header('Sec-WebSocket-Accept',accept);self.end_headers();self.wfile.flush()
                state['connections']+=1
                self.connection.settimeout(1)
                while True:
                    try:
                        payload=state['outgoing'].get_nowait()
                        if payload=='CLOSE':self.connection.sendall(frame(8,struct.pack('!H',1000)));return
                        self.connection.sendall(frame(1,json.dumps(payload)))
                    except queue.Empty:pass
                    if self.connection.pending() or select.select([self.connection],[],[],.02)[0]:
                        opcode,payload=receive(self.connection)
                        if opcode==8:return
                        if opcode==9:
                            state['pings']+=1
                            if state['mode']!='silent':self.connection.sendall(frame(10,payload))
        cls.http=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.load_cert_chain(root/'cert.pem',root/'key.pem')
        cls.http.socket=context.wrap_socket(cls.http.socket,server_side=True)
        cls.host='https://127.0.0.1:'+str(cls.http.server_port)
        threading.Thread(target=cls.http.serve_forever,daemon=True).start()
        cls.pin=certificate_fingerprint(cls.host)
    @classmethod
    def tearDownClass(cls):cls.http.shutdown();cls.http.server_close();cls.temp.cleanup()
    def setUp(self):
        self.data.update(requests=[],connections=0,pings=0,mode='normal',outgoing=queue.Queue())
        self.credentials={'host':self.host,'api_key':'local-test-key','fingerprint':self.pin}
        self.monitor=None;self.ws=None;self.opened=[];self.testdir=tempfile.TemporaryDirectory()
    def tearDown(self):
        if self.monitor:self.monitor.close()
        for connection in self.opened:self.assertIsNone(connection.sock)
        if self.ws:self.ws.close(timeout=.1)
        self.testdir.cleanup()
    def client(self):
        client=Protect(self.credentials)
        original=client.event_socket
        def quick():
            ws=original();self.opened.append(ws);ws.settimeout(.05);return ws
        client.event_socket=quick
        return client
    def start_monitor(self):
        config={'camera_source':'protect','camera_id':'camera-1'}
        self.monitor=Telemetry(Path(self.testdir.name)/'telemetry.json',lambda:config,lambda:self.credentials,
            client_factory=lambda _:self.client(),ping_interval=.15,pong_timeout=.2)
        self.monitor.start()
        eventually(lambda:self.monitor.snapshot()['events_fresh'] and self.monitor.snapshot()['camera_fresh'])
    def test_pinned_wss_receives_camera_event_and_quiet_heartbeat(self):
        self.start_monitor()
        eventually(lambda:self.data['pings']>=1)
        self.data['outgoing'].put({'type':'add','item':{'id':'motion-1','modelKey':'event','type':'motion','device':'camera-1','start':int(time.time()*1000)}})
        eventually(lambda:self.monitor.snapshot()['last_motion'] is not None)
        self.assertTrue(self.monitor.snapshot()['events_fresh'])
        self.assertTrue(self.monitor.snapshot()['motion_active'])
    def test_close_reconnects_without_losing_received_timestamp(self):
        self.start_monitor()
        self.data['outgoing'].put({'type':'add','item':{'id':'motion-1','modelKey':'event','type':'motion','device':'camera-1','start':int(time.time()*1000)}})
        eventually(lambda:self.monitor.snapshot()['last_motion'] is not None)
        saved=self.monitor.snapshot()['last_motion']
        self.data['outgoing'].put('CLOSE')
        eventually(lambda:not self.monitor.snapshot()['events_fresh'])
        self.assertIsNone(self.monitor.snapshot()['motion_active'])
        eventually(lambda:self.data['connections']>=2 and self.monitor.snapshot()['events_fresh'])
        self.assertEqual(self.monitor.snapshot()['last_motion'],saved)
    def test_missing_pong_does_not_leave_connection_green(self):
        self.data['mode']='silent';self.start_monitor()
        eventually(lambda:self.data['pings']>=1)
        eventually(lambda:not self.monitor.snapshot()['events_fresh'])
        self.assertEqual(self.monitor.snapshot()['events_state'],'reconnecting')
    def test_dashboard_and_tv_api_expose_live_received_data_without_secrets(self):
        import server
        self.start_monitor()
        self.data['outgoing'].put({'type':'add','item':{'id':'api-motion','modelKey':'event','type':'motion','device':'camera-1','start':int(time.time()*1000)}})
        eventually(lambda:self.monitor.snapshot()['last_motion'] is not None)
        api=ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
        threading.Thread(target=api.serve_forever,daemon=True).start()
        def call(path,token,body=None):
            connection=http.client.HTTPConnection('127.0.0.1',api.server_port,timeout=3)
            connection.request('POST' if body is not None else 'GET',path,body=json.dumps(body) if body is not None else None,headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'})
            result=connection.getresponse();raw=result.read();connection.close()
            self.assertEqual(result.status,200)
            return json.loads(raw)
        try:
            with patch.object(server,'DATA',Path(self.testdir.name)),patch.object(server,'monitor',self.monitor),patch.object(server,'DEMO',True),patch.object(server,'sessions',{'admin-test':{'expires':time.time()+60}}):
                dashboard=call('/api/status','admin-test')
                access=call('/api/tv/pair','admin-test',{})['token']
                tv=call('/api/tv/status',access)
                self.assertTrue(dashboard['telemetry']['events_fresh'])
                self.assertEqual(tv['telemetry']['last_motion'],dashboard['telemetry']['last_motion'])
                self.assertNotIn('local-test-key',json.dumps(tv));self.assertNotIn(self.host,json.dumps(tv))
        finally:
            api.shutdown();api.server_close()
    def test_wrong_pin_sends_no_key(self):
        self.credentials['fingerprint']='0'*64
        with self.assertRaises(ProtectError):Protect(self.credentials).event_socket()
        self.assertEqual(self.data['requests'],[])
    def test_untrusted_certificate_sends_no_key(self):
        self.credentials['fingerprint']=''
        with self.assertRaises(ProtectError):Protect(self.credentials).event_socket()
        self.assertEqual(self.data['requests'],[])
    def test_no_redirect_can_forward_api_key(self):
        self.data['mode']='redirect'
        with self.assertRaises(ProtectError):Protect(self.credentials).event_socket()
        self.assertEqual(len(self.data['requests']),1)
        self.assertNotIn('stolen-key',self.data['requests'][0][0])
    def test_unsupported_and_unauthorized_endpoint(self):
        for mode,code in (('unsupported',404),('denied',401)):
            self.data['mode']=mode
            with self.assertRaises(ProtectError) as error:Protect(self.credentials).event_socket()
            self.assertEqual(error.exception.code,code)

if __name__=='__main__':unittest.main()
