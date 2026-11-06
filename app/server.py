import json, os, secrets, time, re, threading, urllib.request, urllib.error, sys, hashlib
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from protect import Protect, ProtectError, connection_credentials
from telemetry import Telemetry, inactive
try:
    import release_info
except ModuleNotFoundError:
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'pi'))
    import release_info

DATA=Path(os.getenv('DATA_DIR','./data'))
DATA.mkdir(parents=True,exist_ok=True)
PASSWORD=os.getenv('DASHBOARD_PASSWORD','')
HOME_TEST=os.getenv('HOME_TEST_MODE','false').lower()=='true'
DEMO=HOME_TEST or os.getenv('DEMO_MODE','true').lower()=='true'
AGENT=os.getenv('AGENT_URL','http://127.0.0.1:8091')
TOKEN=os.getenv('AGENT_TOKEN','')
STATIC=Path(__file__).parent/'static'
DEFAULT=dict(camera_name='Eingang',stream_url='',gpio_pin=17,auto_off_minutes=5,github_repo=release_info.REPOSITORY,camera_source='manual',camera_id='',quality='medium')
lock=threading.RLock()
sessions={}
failures={}
monitor=None
catalog_lock=threading.Lock()
catalog_cache={'key':None,'client':None,'rows':[],'until':0,'fresh':False}
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


def camera_rows():
    """Private camera catalog. Stream addresses never leave the server."""
    c=config();cred=credentials()
    rows=[]
    for item in read('manual-cameras.json',[]):
        if isinstance(item,dict) and item.get('id') and item.get('stream_url'):
            rows.append(item | {'source':'manual','available':True,'key':'manual:'+item['id']})
    if c['camera_source']=='manual' and c['stream_url'] and not any(r['stream_url']==c['stream_url'] for r in rows):
        rows.append({'id':c['camera_id'] or 'current','key':'manual:'+(c['camera_id'] or 'current'),
            'name':c['camera_name'],'source':'manual','stream_url':c['stream_url'],'available':True})
    fresh=True
    if cred:
        key=(str(DATA),hashlib.sha256(json.dumps(cred,sort_keys=True).encode()).hexdigest())
        with catalog_lock:
            if catalog_cache['key']!=key:
                catalog_cache.update(key=key,client=None,rows=[],until=0,fresh=False)
            if time.monotonic()>=catalog_cache['until']:
                try:
                    if catalog_cache['client'] is None:catalog_cache['client']=Protect(cred)
                    found=catalog_cache['client'].cameras()
                    catalog_cache.update(rows=found[:128],fresh=True,until=time.monotonic()+60)
                except ProtectError:
                    catalog_cache.update(fresh=False,until=time.monotonic()+10)
            found=list(catalog_cache['rows']);fresh=catalog_cache['fresh']
        rows.extend({'id':r['id'],'key':'protect:'+r['id'],'name':r['name'][:80],
            'source':'protect','available':r['state']=='CONNECTED'} for r in found)
        if not found and c['camera_source']=='protect' and c['camera_id'] and c['stream_url']:
            rows.append({'id':c['camera_id'],'key':'protect:'+c['camera_id'],'name':c['camera_name'],
                'source':'protect','available':True})
    if DEMO and not HOME_TEST and not cred and not rows:
        rows=[{'id':r['id'],'key':'demo:'+r['id'],'name':r['name'],'source':'demo',
            'available':r['state']=='CONNECTED'} for r in DEMO_CAMERAS]
    return rows,fresh


def camera_selection_key(c=None):
    c=c or config()
    return c['camera_source']+':'+(c['camera_id'] or 'current')


def public_cameras():
    rows,fresh=camera_rows();selected=camera_selection_key()
    return {'cameras':[{'id':r['key'],'name':r['name'],'available':r['available'],
        'selected':r['key']==selected,'manual':r['source']=='manual'} for r in rows],
        'selected_camera':selected,'cameras_fresh':fresh}


def choose_camera(key,enable=False):
    if not isinstance(key,str) or not 1<=len(key)<=300:raise ValueError('Bitte eine Kamera auswählen.')
    rows,_=camera_rows()
    camera=next((r for r in rows if r['key']==key),None)
    if not camera or not camera['available']:raise ValueError('Diese Kamera ist gerade nicht erreichbar.')
    previous=config();cred=credentials()
    if camera['source']=='protect':
        if previous['camera_source']=='protect' and previous['camera_id']==camera['id'] and previous['stream_url']:
            stream=previous['stream_url']
        else:
            client=Protect(cred)
            stream=(client.streams(camera['id'],previous['quality'],enable=True) if enable else
                client.streams(camera['id'],previous['quality']))
    elif camera['source']=='demo':
        if not DEMO:raise ValueError('Beispielkameras sind hier nicht verfügbar.')
        stream=''
    else:stream=camera['stream_url']
    with lock:
        latest=config()
        if credentials()!=cred or latest['quality']!=previous['quality']:
            raise ValueError('Die Kameraeinrichtung wurde geändert. Bitte erneut auswählen.')
        apply(latest|{'camera_name':camera['name'],'camera_id':camera['id'],
            'camera_source':camera['source'],'stream_url':stream})


def apply_manual(c):
    """Retain previously entered streams when adding another manual camera."""
    with lock:
        previous=config();stored=read('manual-cameras.json',[])
        rows=list(stored)
        if previous['camera_source']=='manual' and previous['stream_url'] and not any(r['stream_url']==previous['stream_url'] for r in rows):
            rows.append({'id':previous['camera_id'] or 'current','name':previous['camera_name'],'stream_url':previous['stream_url']})
        existing=next((r for r in rows if r['stream_url']==c['stream_url']),None)
        if existing:
            selected=existing['id'];rows=[r|{'name':c['camera_name']} if r['id']==selected else r for r in rows]
        else:
            if len(rows)>=24:raise ValueError('Es sind bereits 24 eigene Kameras gespeichert.')
            selected=secrets.token_hex(12)
            rows.append({'id':selected,'name':c['camera_name'],'stream_url':c['stream_url']})
        apply(c|{'camera_id':selected})
        try:save('manual-cameras.json',rows)
        except Exception:
            apply(previous)
            raise

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


class MaintenanceError(ValueError):
    def __init__(self,message,code=503):
        super().__init__(message)
        self.code=code


def maintenance_request(path,body=None):
    if len(TOKEN)<24:
        raise MaintenanceError('Browser-Updates benötigen die einmalige Einrichtung des Pi-Wartungsdiensts.')
    request=urllib.request.Request('http://127.0.0.1:8093/'+path,
        data=json.dumps(body).encode() if body is not None else None,
        headers={'Authorization':'Bearer '+TOKEN,'Content-Type':'application/json'})
    try:
        with urllib.request.urlopen(request,timeout=12 if path=='update' else 3) as response:
            raw=response.read(65537)
            if len(raw)>65536: raise ValueError('Ungültige Antwort des Wartungsdiensts.')
            return json.loads(raw)
    except urllib.error.HTTPError as error:
        try: message=json.loads(error.read(8192)).get('error')
        except (ValueError,TypeError): message=None
        raise MaintenanceError(message or 'Wartungsdienst konnte den Auftrag nicht ausführen.',error.code if error.code in (401,409,503) else 503) from None
    except (OSError,ValueError):
        raise MaintenanceError('Pi-Wartungsdienst nicht erreichbar. Browser-Updates einmalig einrichten beziehungsweise Dienst prüfen.') from None


def maintenance_status():
    if DEMO:
        return {'available':False,'persistent':False,'job':None,'message':'Im Heimtest werden keine Pi-Updates installiert.'}
    try:
        return maintenance_request('status')
    except ValueError as error:
        return {'available':False,'persistent':False,'job':None,'message':str(error)}


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
                    'remaining_seconds':result.get('remaining_seconds',0),'auto_off_minutes':c['auto_off_minutes'],'available':available,'telemetry':telemetry_status()}|public_cameras())
            if self.path.startswith('/api/'):
                if not self.authorized(): return self.send({'error':'Bitte erneut anmelden.','reauth':True},401)
                if self.path=='/api/status':
                    result,available=playback_state()
                    c=config(); cred=credentials()
                    return self.send({'demo':DEMO,'home_test':HOME_TEST,'version':os.getenv('APP_VERSION','dev'),'state':result,'agent_available':available,'config':public_config(c),
                        'telemetry':telemetry_status(),'maintenance':maintenance_status(),'protect':{'configured':bool(cred),'host':cred.get('host',''),'pinned':bool(cred.get('fingerprint')),
                        'auth_mode':cred.get('auth_mode','api_key') if cred else 'local','username':cred.get('username',''),
                        'has_api_key':bool(cred.get('api_key')),'has_password':bool(cred.get('password'))}})
                if self.path=='/api/update':
                    info=release_info.release(refresh=True)
                    current=os.getenv('APP_VERSION','dev')
                    try: available=release_info.newer(info['version'],current)
                    except ValueError: available=info['version']!=current
                    support=maintenance_status()
                    return self.send(info|{'current':current,'available':available,'maintenance':support,
                        'can_install':bool(available and support.get('available') and support.get('persistent') and not (support.get('job') or {}).get('busy')),
                        'message':'Einstellungen werden vor der Installation gesichert.'})
                if self.path=='/api/update/status':
                    return self.send(maintenance_status())
                if self.path=='/api/cameras':
                    return self.send(public_cameras())
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
            if self.path=='/api/update/progress':
                watch=body.get('watch')
                if not isinstance(watch,str) or not 32<=len(watch)<=128:
                    return self.send({'error':'Statusfreigabe ungültig.'},401)
                return self.send(maintenance_request('watch',{'watch':watch}))
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
                if set(body)-{'action','camera_id'} or ('camera_id' in body and body['action']!='on'):
                    raise ValueError('Ungültige Kameraaktion.')
                if 'camera_id' in body:
                    if not DEMO and (maintenance_status().get('job') or {}).get('busy'):
                        raise MaintenanceError('Die Kameras werden gerade aktualisiert. Bitte kurz warten.',409)
                    try:choose_camera(body['camera_id'])
                    except ProtectError:
                        raise ValueError('Diese Kamera ist gerade nicht verfügbar. Bitte um Hilfe bitten.') from None
                return self.send(perform_action(body['action']))
            if not self.authorized(): return self.send({'error':'Bitte erneut anmelden.','reauth':True},401)
            if self.path in ('/api/config','/api/protect/connect','/api/protect/select','/api/tv/revoke','/api/cameras/select','/api/cameras/remove') and not DEMO:
                job=maintenance_status().get('job') or {}
                if job.get('busy'):
                    return self.send({'error':'Aktualisierung läuft. Einstellungen danach ändern.'},409)
            if self.path=='/api/update/install':
                if DEMO: raise ValueError('Im Heimtest werden keine Pi-Updates installiert.')
                if body.get('confirm') is not True or set(body)-{'version','confirm'}:
                    raise ValueError('Die ausgewählte Version zuerst in der Oberfläche bestätigen.')
                release_info.version(body.get('version'))
                return self.send(maintenance_request('update',{'version':body['version']}),202)
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
                with lock:
                    c=valid_config(body)
                    if body.get('stream_url'):apply_manual(c)
                    else:apply(c)
                return self.send({'message':'Einstellungen gespeichert.'})
            if self.path=='/api/cameras/select':
                if 'camera_id' not in body or set(body)-{'camera_id','enable_stream'} or type(body.get('enable_stream',False)) is not bool:
                    raise ValueError('Bitte eine Kamera auswählen.')
                choose_camera(body['camera_id'],enable=body.get('enable_stream',False))
                return self.send({'message':'Startkamera gespeichert.'})
            if self.path=='/api/cameras/remove':
                if set(body)!={'camera_id'} or not isinstance(body['camera_id'],str):raise ValueError('Ungültige Kamera.')
                with lock:
                    if body['camera_id']==camera_selection_key():raise ValueError('Zuerst eine andere Startkamera auswählen.')
                    rows=read('manual-cameras.json',[])
                    kept=[r for r in rows if 'manual:'+r['id']!=body['camera_id']]
                    if len(kept)==len(rows):raise ValueError('Nur eigene gespeicherte Kameras können entfernt werden.')
                    save('manual-cameras.json',kept)
                return self.send({'message':'Kamera entfernt.'})
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
            if self.path=='/api/protect/preview':
                if body:
                    raise ValueError('Die Vorschau verwendet ausschließlich die eingerichtete Kamera.')
                selected=config()
                cred=credentials()
                if selected.get('camera_source')!='protect' or not selected.get('camera_id') or not cred:
                    raise ValueError('Zuerst eine Protect-Kamera verbinden und übernehmen.')
                return self.send(Protect(cred).snapshot(selected['camera_id']),content_type='image/jpeg')
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
        except MaintenanceError as e: self.send({'error':str(e)},e.code)
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
