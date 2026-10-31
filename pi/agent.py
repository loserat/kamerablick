"""Local GPIO/CEC/player service. Runs as the graphical-session user."""
import json, os, secrets, subprocess, threading, time
from pathlib import Path
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from cec_bridge import CecBridge, RemoteInput
from player_health import PlayerHealth

class Controller:
    def __init__(self,path,button_factory=None,clock=time.monotonic):
        self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True)
        self.settings=json.loads(self.path.read_text()) if self.path.exists() else {'gpio_pin':17,'auto_off_minutes':5,'stream_url':''}
        self.button_factory=button_factory;self.clock=clock
        self.lock=threading.RLock()
        self.remote=RemoteInput();self.bridge=CecBridge(self.remote)
        self.player=None;self.button=None;self.want_on=False;self.deadline=0;self.retry_at=0;self.retries=0
        self.health=PlayerHealth(clock);self.player_socket=None
        self.message='Bereit. TV-Zustand wird nicht ausgelesen.'

    def configure(self,c):
        pin=int(c['gpio_pin']);minutes=int(c['auto_off_minutes'])
        if not 0<=pin<=27 or not 0<=minutes<=120: raise ValueError('Ungültige Einstellung')
        if c['stream_url'] and not c['stream_url'].startswith(('rtsp://','rtsps://')): raise ValueError('Ungültiger Stream')
        factory=self.button_factory
        if factory is None:
            from gpiozero import Button
            factory=Button
        new_button=None
        old_pin=self.settings.get('gpio_pin')
        if self.button is None or pin!=old_pin:
            # Request the replacement before releasing a working GPIO.
            new_button=factory(pin,pull_up=True,bounce_time=0.2)
            new_button.when_pressed=self.press
        try:
            tmp=self.path.with_suffix('.tmp')
            fd=os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
            with os.fdopen(fd,'w') as f: json.dump(c,f)
            os.chmod(tmp,0o600);tmp.replace(self.path)
        except Exception:
            if new_button: new_button.close()
            raise
        if new_button:
            if self.button: self.button.close()
            self.button=new_button
        stream_changed=c['stream_url']!=self.settings.get('stream_url')
        self.settings=c
        if self.want_on:
            self.deadline=self.clock()+minutes*60 if minutes else 0
            if stream_changed:
                self.stop_player();self.retry_at=0;self.retries=0
                self.message='Kamera geändert. Wiedergabe wird neu gestartet.'

    def press(self):
        try:
            with self.lock: self.action('toggle')
        except Exception:
            self.message='Tasteraktion fehlgeschlagen. CEC und Kamera prüfen.'

    def cec(self,commands):
        self.bridge.command('off' if commands=='standby 0\n' else 'on')

    def start_player(self):
        # A dedicated exit code distinguishes Back/OK from network/player failures.
        keys=self.path.parent/'tv-input.conf'
        keys.write_text('ESC quit 42\nBS quit 42\nENTER quit 42\n')
        directory=self.path.parent/'player'
        directory.mkdir(mode=0o700,exist_ok=True)
        if directory.is_symlink(): raise OSError('Privates Player-Verzeichnis erforderlich')
        directory.chmod(0o700)
        self.player_socket=directory/('p-'+secrets.token_hex(6)+'.sock')
        self.player=subprocess.Popen(['mpv','--no-config','--load-scripts=no','--fullscreen','--no-terminal','--no-input-default-bindings','--input-conf='+str(keys),'--input-ipc-server='+str(self.player_socket),'--rtsp-transport=tcp','--network-timeout=10','--',self.settings['stream_url']],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        self.health.begin(self.player_socket)

    def stop_player(self):
        if self.player and self.player.poll() is None:
            self.player.terminate()
            try: self.player.wait(timeout=3)
            except subprocess.TimeoutExpired: self.player.kill();self.player.wait()
        self.player=None
        self.health.clear()
        if self.player_socket:
            self.player_socket.unlink(missing_ok=True);self.player_socket=None

    def status(self):
        running=self.player is not None and self.player.poll() is None
        health=self.health.snapshot()
        if not running:
            health=health|{'progress_fresh':False,'stable':False,'state':'reconnecting' if self.want_on else 'stopped'}
        label='Wiedergabezeit läuft' if running and health['progress_fresh'] else 'Videofortschritt fehlt' if running and health['state'] in ('stalled','unavailable') else 'Kamera wird verbunden' if self.want_on else 'Wiedergabe aus'
        return {'active':self.want_on,'player_running':running,'player_health':health,'tv':label,
                'remaining_seconds':max(0,int(self.deadline-self.clock())) if self.deadline else 0,
                'message':self.message,'gpio_pin':self.settings['gpio_pin'],'cec':self.bridge.snapshot()}

    def action(self,command):
        if command=='toggle': command='off' if self.want_on else 'on'
        if command=='on':
            if not self.settings.get('stream_url'): raise ValueError('Stream-Adresse fehlt')
            if not self.want_on:
                self.cec('on 0\nas\n')
                self.want_on=True;self.retry_at=0;self.retries=0
                try: self.start_player()
                except OSError:
                    self.retry_at=self.clock()+5;self.retries=1
            minutes=int(self.settings.get('auto_off_minutes',5))
            self.deadline=self.clock()+minutes*60 if minutes else 0
            pending=self.player is None or self.player.poll() is not None
            self.message='Videoplayer konnte nicht starten. Neuer Versuch folgt.' if self.retry_at and pending else 'Einschalten angefordert. TV-Bild vor Ort prüfen.'
        elif command=='menu':
            self.want_on=False;self.deadline=0;self.retry_at=0
            self.stop_player()
            self.message='Kameraansicht geschlossen. Fernseher bleibt eingeschaltet.'
        elif command=='off':
            self.want_on=False;self.deadline=0;self.retry_at=0
            self.stop_player()
            self.message='Wiedergabe beendet. Standby wird angefordert.'
            try: self.cec('standby 0\n')
            except Exception:
                self.message='Wiedergabe beendet, TV-Standby fehlgeschlagen. TV prüfen.'
                raise
            self.message='Standby gesendet. TV-Zustand nicht bestätigt.'
        elif command!='status': raise ValueError('Unbekannte Aktion')
        return self.status()

    def tick(self):
        for key in self.remote.take():
            if self.want_on:
                if key in ('Enter','Escape'): self.action('menu')
                # Do not forward the same OK/Back into the newly shown menu.
            else: self.remote.publish(key)
        now=self.clock()
        if self.want_on and self.player is not None and self.player.poll()==42:
            self.action('menu')
            return
        if self.want_on and self.deadline and now>=self.deadline:
            try: self.action('off')
            except Exception: pass
            return
        if self.want_on and self.player is not None and self.player.poll() is None:
            self.health.sample()
            health=self.health.snapshot()
            if health['restart_due']:
                self.stop_player()
                self.retry_at=now+min(60,5*2**min(self.retries,4))
                self.message='Kein Videofortschritt. Die Kamera wird erneut verbunden.'
                return
            if health['stable']:
                self.retries=0;self.retry_at=0
        if self.want_on and (self.player is None or self.player.poll() is not None) and now>=self.retry_at:
            self.stop_player();self.retries+=1
            try:
                self.start_player()
                self.message='Videoplayer neu gestartet. Wiedergabefortschritt wird geprüft.'
            except OSError: self.message='Videoplayer nicht verfügbar. Installation auf dem Pi prüfen.'
            self.retry_at=now+min(60,5*2**min(self.retries-1,4))

    def timer(self):
        while True:
            time.sleep(0.1)
            with self.lock: self.tick()

def serve():
    token=os.getenv('AGENT_TOKEN','')
    if len(token)<24: raise SystemExit('AGENT_TOKEN muss mindestens 24 Zeichen haben')
    controller=Controller(os.getenv('AGENT_CONFIG',str(Path.home()/'.config/oma-tv/config.json')))
    controller.configure(controller.settings)
    controller.bridge.start()
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args): pass
        def do_POST(self):
            if self.path!='/action': self.send_response(404);self.end_headers();return
            if not secrets.compare_digest(self.headers.get('Authorization',''),'Bearer '+token):
                self.send_response(401);self.end_headers();return
            try:
                size=int(self.headers.get('Content-Length',0))
                if not 0<size<=16384: raise ValueError('Anfrage zu groß')
                data=json.loads(self.rfile.read(size))
                if data['action']=='remote_poll': result=controller.remote.poll(data.get('input',{}))
                else:
                    with controller.lock:
                        if data['action']=='configure': controller.configure(data['config']);result={'message':'Pi-Einstellungen übernommen.'}
                        else: result=controller.action(data['action'])
                code=200
            except Exception: result={'error':'Pi-Aktion fehlgeschlagen. Kamera, CEC und GPIO prüfen.'};code=502
            raw=json.dumps(result).encode()
            self.send_response(code);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
    threading.Thread(target=controller.timer,daemon=True).start()
    try: ThreadingHTTPServer(('127.0.0.1',8091),Handler).serve_forever()
    finally: controller.bridge.close();controller.stop_player();controller.button.close()

if __name__=='__main__': serve()
