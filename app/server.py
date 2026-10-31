import json, os, secrets, time, re, threading, urllib.request, urllib.error
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from protect import Protect, ProtectError, connection_credentials
from telemetry import Telemetry, inactive

DATA=Path(os.getenv('DATA_DIR','./data'))
DATA.mkdir(parents=True,exist_ok=True)
PASSWORD=os.getenv('DASHBOARD_PASSWORD','')
HOME_TEST=os.getenv('HOME_TEST_MODE','false').lower()=='true'
DEMO=HOME_TEST or os.getenv('DEMO_MODE','true').lower()=='true'
AGENT=os.getenv('AGENT_URL','http://127.0.0.1:8091')
TOKEN=os.getenv('AGENT_TOKEN','')
STATIC=Path(__file__).parent/'static'
DEFAULT=dict(camera_name='Eingang',stream_url='',gpio_pin=17,auto_off_minutes=5,github_repo='',camera_source='manual',camera_id='',quality='medium')
lock=threading.RLock()
sessions={}
failures={}
monitor=None
state={'tv':'Wiedergabe aus','message':'Heimtest – keine TV-/GPIO-Befehle' if HOME_TEST else 'Demomodus – keine Hardware verbunden','active':False,'remaining_seconds':0}
DEMO_CAMERAS=[{'id':'demo-entry','name':'Haustür','model':'Beispielkamera','state':'CONNECTED'}, {'id':'demo-garden','name':'Garten','model':'Beispielkamera','state':'CONNECTED'},{'id':'demo-garage','name':'Garage','model':'Beispielkamera','state':'DISCONNECTED'}]

def read(name,default):
    with lock:
        p=DATA/name
        return json.loads(p.read_text()) if p.exists() else default

def save(name,value):
    with lock:
        tmp=DATA/(name+'.tmp')
        fd=os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
        with os.fdopen(fd,'w') as f: json.dump(value,f)
        os.chmod(tmp,0o600)
        tmp.replace(DATA/name)

def config(): return DEFAULT | read('config.json',{})
def credentials(): return read('protect.json',{})
def public_config(c): return {k:v for k,v in c.items() if k!='stream_url'} | {'has_stream':bool(c['stream_url'])}

def agent(action,settings=None,remote_input=None):
    # The API key is deliberately never sent to the hardware service.
    payload={'action':action,'input':remote_input} if action=='remote_poll' else {'action':action,'config':settings or config()}
    req=urllib.request.Request(AGENT+'/action',data=json.dumps(payload).encode(),headers={'Authorization':'Bearer '+TOKEN,'Content-Type':'application/json'})
    try:
        with urllib.request.urlopen(req,timeout=1 if action=='remote_poll' else 15) as r: return json.load(r)
    except (OSError,ValueError): raise ValueError('Pi-Dienst nicht erreichbar oder Aktion fehlgeschlagen. Diagnose auf dem Pi prüfen.')

def apply(c):
    if not DEMO: agent('configure',c)
    save('config.json',c)

def valid_config(body):
    c=config()
    for k in ('camera_name','stream_url','gpio_pin','auto_off_minutes','github_repo'):
        if k in body: c[k]=body[k]
    for field,low,high in [('gpio_pin',0,27),('auto_off_minutes',0,120)]:
        raw=c[field]
        if isinstance(raw,bool) or not re.fullmatch(r'\d+',str(raw)): raise ValueError('GPIO und Abschaltzeit müssen ganze Zahlen sein.')
        c[field]=int(raw)
        if not low<=c[field]<=high: raise ValueError('GPIO oder Abschaltzeit außerhalb des erlaubten Bereichs.')
    for field in ('camera_name','github_repo','stream_url'):
        if not isinstance(c[field],str): raise ValueError('Ungültige Texteingabe.')
        c[field]=c[field].strip()
    if not c['camera_name'] or len(c['camera_name'])>80: raise ValueError('Kameraname muss 1 bis 80 Zeichen haben.')
    if c['github_repo'] and not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',c['github_repo']): raise ValueError('GitHub-Repository als Besitzer/Name eingeben.')
    if c['stream_url'] and not c['stream_url'].startswith(('rtsp://','rtsps://')): raise ValueError('RTSP- oder RTSPS-Adresse erforderlich.')
    if 'stream_url' in body:
        c.update(camera_source='manual',camera_id='')
    return c

def playback_state():
    if DEMO:
        with lock:
            if state.get('deadline'):
                remaining=max(0,int(state['deadline']-time.monotonic()))
                state['remaining_seconds']=remaining
                if not remaining:
                    state.update(active=False,tv='Wiedergabe aus',deadline=0,message='Demo: automatische Abschaltung ausgeführt.')
            return dict(state),True
    try: return agent('status'),True
    except ValueError as e: return {'tv':'Unbekannt','active':False,'message':str(e)},False

def perform_action(action):
    if action not in ('on','off','toggle','menu'): raise ValueError('Unbekannte Aktion.')
    if DEMO:
        with lock:
            active=not state['active'] if action=='toggle' else action=='on'
            minutes=config()['auto_off_minutes']
            state.update(active=active,tv='Wiedergabe läuft (Demo)' if active else 'Wiedergabe aus',
                message='Demoaktion ausgeführt – kein TV-Befehl gesendet.',
                deadline=time.monotonic()+minutes*60 if active and minutes else 0,remaining_seconds=minutes*60 if active else 0)
            return {'message':state['message']}
    if action in ('on','toggle') and config()['camera_source']=='demo': raise ValueError('Bitte zuerst eine echte Kamera einrichten.')
    return agent(action)

def telemetry_status():
    if monitor is not None:
        return monitor.snapshot()
    c=config()
    return inactive('demo' if c.get('camera_source')=='demo' else 'manual' if c.get('stream_url') else 'unconfigured')

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def send(self,value,code=200,content_type='application/json'):
        body=value if isinstance(value,bytes) else json.dumps(value).encode()
        self.send_response(code)
        self.send_header('Content-Type',content_type)
        self.send_header('Content-Length',str(len(body)))
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('X-Frame-Options','DENY')
        self.send_header('Referrer-Policy','no-referrer')
        self.send_header('Content-Security-Policy',"default-src 'self'; img-src 'self' blob: data:; style-src 'self'; script-src 'self'; frame-ancestors 'none'")
        self.end_headers()
        try: self.wfile.write(body)
        except (BrokenPipeError,ConnectionResetError): pass
    def sid(self): return self.headers.get('Authorization','').removeprefix('Bearer ')
    def authorized(self):
        with lock:
            s=sessions.get(self.sid())
            return bool(s and s['expires']>time.time())
    def tv_authorized(self):
        access=read('tv-access.json',{}).get('token','')
        return bool(access and secrets.compare_digest(self.sid(),access))
    def do_GET(self):
        try:
            if self.path=='/healthz': return self.send({'ok':True})
            if self.path=='/api/tv/status':
                if not self.tv_authorized(): return self.send({'error':'TV-Ansicht bitte einmal im Dashboard freigeben.','reauth':True},401)
                result,available=playback_state();c=config()
                return self.send({'demo':DEMO,'camera_name':c['camera_name'],'ready':DEMO or (available and bool(c['stream_url']) and c['camera_source']!='demo'),
                    'active':bool(result.get('active')),'player_running':bool(result.get('player_running',False)),
                    'playback_progress':bool(result.get('player_health',{}).get('progress_fresh')),
                    'remaining_seconds':result.get('remaining_seconds',0),'auto_off_minutes':c['auto_off_minutes'],'available':available,'telemetry':telemetry_status()})
            if self.path.startswith('/api/'):
                if not self.authorized(): return self.send({'error':'Bitte erneut anmelden.','reauth':True},401)
                if self.path=='/api/status':
                    result,available=playback_state()
                    c=config(); cred=credentials()
                    return self.send({'demo':DEMO,'home_test':HOME_TEST,'version':os.getenv('APP_VERSION','dev'),'state':result,'agent_available':available,'config':public_config(c),
                        'telemetry':telemetry_status(),'protect':{'configured':bool(cred),'host':cred.get('host',''),'pinned':bool(cred.get('fingerprint')),
                        'auth_mode':cred.get('auth_mode','api_key') if cred else 'local','username':cred.get('username',''),
                        'has_api_key':bool(cred.get('api_key')),'has_password':bool(cred.get('password'))}})
                if self.path=='/api/update':
                    repo=config()['github_repo']
                    if not repo: raise ValueError('Zuerst ein GitHub-Repository in den Einstellungen eintragen.')
                    try:
                        req=urllib.request.Request('https://api.github.com/repos/'+repo+'/releases/latest',headers={'Accept':'application/vnd.github+json','User-Agent':'oma-tv'})
                        with urllib.request.urlopen(req,timeout=8) as r: release=json.load(r)
                        return self.send({'version':release['tag_name'],'current':os.getenv('APP_VERSION','dev'),'message':'Installation über den privaten Wartungszugang.'})
                    except (OSError,ValueError,KeyError): return self.send({'error':'Kein öffentliches GitHub-Release erreichbar. Repository und Verbindung prüfen.'},502)
                return self.send({'error':'Nicht gefunden'},404)
            name={'/':'index.html','/app.js':'app.js','/style.css':'style.css','/tv':'tv.html','/tv/':'tv.html','/tv.css':'tv.css','/tv.js':'tv.js','/tv-navigation.js':'tv-navigation.js','/tv-remote.js':'tv-remote.js','/telemetry-view.js':'telemetry-view.js','/icon.svg':'icon.svg','/icon-512.png':'icon-512.png','/apple-touch-icon.png':'apple-touch-icon.png'}.get(self.path)
            if not name: return self.send({'error':'Nicht gefunden'},404)
            kind={'html':'text/html; charset=utf-8','js':'text/javascript; charset=utf-8','css':'text/css; charset=utf-8','svg':'image/svg+xml','png':'image/png'}[name.split('.')[-1]]
            return self.send((STATIC/name).read_bytes(),content_type=kind)
        except ValueError as e: self.send({'error':str(e)},400)
        except Exception: self.send({'error':'Anfrage fehlgeschlagen. Bitte erneut versuchen.'},500)
    def do_POST(self):
        try:
            length=int(self.headers.get('Content-Length',0))
            if not 0<length<=16384: return self.send({'error':'Ungültige Anfragegröße'},413)
            body=json.loads(self.rfile.read(length))
            if not isinstance(body,dict): raise ValueError('Ungültige Anfrage.')
            if self.path=='/api/login':
                now=time.time(); ip=self.client_address[0]
                with lock:
                    attempts=[t for t in failures.get(ip,[]) if t>now-60]
                    failures[ip]=attempts
                    if len(attempts)>=8: return self.send({'error':'Zu viele Anmeldeversuche. Bitte eine Minute warten.'},429)
                    if not PASSWORD or not secrets.compare_digest(str(body.get('password','')),PASSWORD):
                        attempts.append(now)
                        return self.send({'error':'Passwort falsch.'},401)
                    for key in list(sessions):
                        if sessions[key]['expires']<now: sessions.pop(key,None)
                    if len(sessions)>=100: sessions.pop(next(iter(sessions)))
                    sid=secrets.token_urlsafe(32);sessions[sid]={'expires':now+43200,'pending':None}
                    failures.pop(ip,None)
                return self.send({'token':sid})
            if self.path=='/api/tv/provision':
                # Trusted local Pi launcher uses the existing host-agent credential.
                if self.client_address[0] not in ('127.0.0.1', '::1') or len(TOKEN)<24 or not secrets.compare_digest(self.sid(), TOKEN):
                    return self.send({'error':'Lokaler Pi-Zugang erforderlich.'},401)
                with lock:
                    access=read('tv-access.json',{})
                    if not access.get('token'):
                        access={'token':secrets.token_urlsafe(32)}
                        save('tv-access.json',access)
                    receiver=read('tv-receiver.json',{})
                    if not receiver.get('token'):
                        receiver={'token':secrets.token_urlsafe(32)}
                        save('tv-receiver.json',receiver)
                return self.send(access | {'receiver':receiver['token']})
            if self.path=='/api/tv/input':
                receiver=read('tv-receiver.json',{}).get('token','')
                if not receiver or not secrets.compare_digest(self.sid(),receiver):
                    return self.send({'error':'Lokaler TV-Empfänger erforderlich.'},401)
                if DEMO: return self.send({'boot':'demo','cursor':0,'events':[]})
                return self.send(agent('remote_poll',remote_input=body))
            if self.path=='/api/tv/action':
                if not self.tv_authorized(): return self.send({'error':'TV-Ansicht bitte einmal im Dashboard freigeben.','reauth':True},401)
                if body.get('action') not in ('on','off','menu'): raise ValueError('Diese Aktion ist in der TV-Ansicht nicht verfügbar.')
                return self.send(perform_action(body['action']))
            if not self.authorized(): return self.send({'error':'Bitte erneut anmelden.','reauth':True},401)
            if self.path=='/api/tv/pair':
                with lock:
                    access=read('tv-access.json',{})
                    if not access.get('token'):
                        access={'token':secrets.token_urlsafe(32)}
                        save('tv-access.json',access)
                return self.send(access)
            if self.path=='/api/tv/revoke':
                save('tv-access.json',{})
                save('tv-receiver.json',{})
                return self.send({'message':'TV-Zugang zurückgesetzt. TV-Ansicht erneut über das Dashboard öffnen.'})
            if self.path=='/api/logout':
                with lock: sessions.pop(self.sid(),None)
                return self.send({'message':'Abgemeldet'})
            if self.path=='/api/config':
                with lock: apply(valid_config(body))
                return self.send({'message':'Einstellungen gespeichert.'})
            if self.path=='/api/protect/connect':
                is_demo=body.get('demo') is True
                if is_demo:
                    if not DEMO: raise ValueError('Beispielkameras sind nur im Demomodus verfügbar.')
                    pending={'demo':True,'cameras':DEMO_CAMERAS,'expires':time.time()+900}
                else:
                    cred=connection_credentials(body,credentials())
                    rows=Protect(cred).cameras()
                    pending={'demo':False,'credentials':cred,'cameras':rows,'expires':time.time()+900}
                with lock: sessions[self.sid()]['pending']=pending
                return self.send({'cameras':pending['cameras'],'demo':is_demo,'message':'Beispielkameras geladen.' if is_demo else 'Protect verbunden. Kamera auswählen.'})
            if self.path=='/api/protect/test':
                cred=credentials()
                if not cred: raise ValueError('Zuerst einen NVR verbinden und eine Kamera übernehmen.')
                start=time.monotonic()
                client=Protect(cred)
                rows=client.cameras()
                c=config()
                selected=next((row for row in rows if row['id']==c['camera_id']),None)
                if not selected: raise ValueError('Die gespeicherte Kamera ist für diesen NVR-Zugang nicht verfügbar.')
                image=client.snapshot(selected['id'])
                stream=client.streams(selected['id'],c['quality'])
                return self.send({'message':'NVR-Anmeldung, Kameraliste, Standbild und Stream-Adresse sind geprüft. Das Livebild am Fernseher separat prüfen.',
                    'camera_name':selected['name'],'camera_state':selected['state'],'camera_count':len(rows),
                    'snapshot_ok':bool(image),'stream_configured':bool(stream),'elapsed_ms':round((time.monotonic()-start)*1000),
                    'hardware_tested':False})
            if self.path in ('/api/protect/select','/api/protect/snapshot'):
                pending=sessions[self.sid()].get('pending')
                if not pending or pending['expires']<time.time(): raise ValueError('Bitte Protect erneut verbinden. Die Einrichtung ist abgelaufen.')
                camera=next((c for c in pending['cameras'] if c['id']==body.get('camera_id')),None)
                if not camera: raise ValueError('Bitte eine Kamera aus der Liste auswählen.')
                if self.path=='/api/protect/snapshot':
                    if pending['demo']: return self.send({'error':'Beispielkamera: kein echtes Kamerabild verfügbar.'},409)
                    return self.send(Protect(pending['credentials']).snapshot(camera['id']),content_type='image/jpeg')
                quality=body.get('quality','medium')
                if quality not in ('high','medium','low'): raise ValueError('Ungültige Bildqualität.')
                if camera['state']!='CONNECTED': raise ValueError('Diese Kamera ist nicht verbunden. Bitte eine erreichbare Kamera auswählen.')
                if pending['demo']:
                    stream='';source='demo'
                else:
                    stream=Protect(pending['credentials']).streams(camera['id'],quality,body.get('enable_stream') is True)
                    source='protect'
                c=config() | {'camera_name':camera['name'],'stream_url':stream,'camera_source':source,'camera_id':camera['id'],'quality':quality}
                with lock:
                    apply(c)
                    if not pending['demo']: save('protect.json',pending['credentials'])
                return self.send({'message':'Kamera übernommen.' if not pending['demo'] else 'Beispielkamera übernommen – keine echte Verbindung.'})
            if self.path=='/api/action':
                return self.send(perform_action(body.get('action')))
            return self.send({'error':'Nicht gefunden'},404)
        except ProtectError as e: self.send({'error':str(e),**e.details},e.code)
        except (ValueError,TypeError,KeyError) as e: self.send({'error':str(e)},400)
        except Exception: self.send({'error':'Aktion fehlgeschlagen. Einstellungen und Pi-Dienst prüfen.'},502)

if __name__=='__main__':
    if not PASSWORD: raise SystemExit('DASHBOARD_PASSWORD muss gesetzt sein')
    if not DEMO and len(TOKEN)<24: raise SystemExit('AGENT_TOKEN muss mindestens 24 Zeichen haben')
    monitor=Telemetry(DATA/'telemetry.json', config, credentials)
    try:
        monitor.start()
    except ImportError:
        raise SystemExit('WebSocket-Abhängigkeit fehlt. requirements.txt in der Projektumgebung installieren.')
    try:
        ThreadingHTTPServer((os.getenv('BIND','127.0.0.1'),int(os.getenv('PORT','8088'))),Handler).serve_forever()
    finally:
        monitor.close()
