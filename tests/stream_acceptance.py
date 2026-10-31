"""Real RTSPS/RTSP recovery in an internal Docker network; no real camera or TV."""
import json
import hashlib
from pathlib import Path
import secrets
import shutil
import subprocess
import tempfile
import time

SOURCE=Path(__file__).resolve().parents[1]
SERVER_IMAGE='bluenviron/mediamtx:1.21.3@sha256:59e43552f3be43695b70c19424dc2a42fcec18075f88d91561a24ac5d70a586c'
CONSUMER='''import json,subprocess,time,traceback
from pathlib import Path
from unittest.mock import patch
import agent
state=Path('/state');launches=[];commands=[];real_popen=subprocess.Popen
def headless(args,**kwargs):
 assert args[0]=='mpv'
 split=args.index('--')
 p=real_popen(args[:split]+['--vo=null','--ao=null']+args[split:],**kwargs)
 launches.append(p.pid);return p
c=agent.Controller('/tmp/kamerablick/config.json')
c.settings.update(stream_url='rtsps://stream-server:8322/camera',auto_off_minutes=5)
c.cec=commands.append
sequence=None
with patch.object(agent.subprocess,'Popen',headless):
 try:
  while True:
   try:command=json.loads((state/'control.json').read_text())
   except (FileNotFoundError,json.JSONDecodeError):command=None
   if command is not None:
    if command['seq']!=sequence:
     sequence=command['seq']
     if command['action']=='switch_rtsp':
      c.action('menu');c.settings['stream_url']='rtsp://stream-server:8554/camera';c.action('on')
     else:c.action(command['action'])
   c.tick()
   data=c.status()|{'generation':len(launches),'player_pid':c.player.pid if c.player else None,
                   'deadline':c.deadline,'tv_commands':commands,'sequence':sequence,
                   'retry_scheduled':bool(c.retry_at),'retry_count':c.retries}
   temporary=state/'status.tmp';temporary.write_text(json.dumps(data));temporary.replace(state/'status.json')
   time.sleep(.1)
 except BaseException:
  (state/'failure.txt').write_text(traceback.format_exc())
  raise
 finally:c.stop_player()
'''


def main():
    ident=secrets.token_hex(6)
    network='kamerablick-stream-'+ident
    image='kamerablick-stream-client:'+ident
    server='kamerablick-stream-server-'+ident
    publisher='kamerablick-stream-publisher-'+ident
    consumer='kamerablick-stream-consumer-'+ident
    report={'scope':'Real RTSPS and RTSP test video in an internal Docker network; no Protect console, HDMI, GPIO, IR remote or VPN',
            'clock':'Real monotonic clock and production watchdog/retry thresholds','checks':[]}
    def run(args,check=True,timeout=120):
        p=subprocess.run(args,capture_output=True,text=True,timeout=timeout)
        if check and p.returncode:
            raise RuntimeError('Test command failed: '+args[0]+'\n'+p.stdout[-2000:]+'\n'+p.stderr[-2000:])
        return p
    with tempfile.TemporaryDirectory(prefix='kamerablick-stream-',dir='/tmp') as directory:
        root=Path(directory).resolve();state=root/'state';state.mkdir();cert=root/'cert';cert.mkdir()
        def status():
            if (state/'failure.txt').exists():raise RuntimeError((state/'failure.txt').read_text())
            try:
                data=json.loads((state/'status.json').read_text())
                assert not data.get('player_health',{}).get('progress_fresh') or data.get('player_running') is True
                return data
            except (FileNotFoundError,json.JSONDecodeError):return {}
        def wait_for(predicate,label,seconds=45):
            end=time.monotonic()+seconds
            while time.monotonic()<end:
                data=status()
                if predicate(data):return data
                time.sleep(.1)
            raise AssertionError(label+'\n'+json.dumps(status()))
        def command(action,seq):
            tmp=state/'control.tmp';tmp.write_text(json.dumps({'action':action,'seq':seq}));tmp.replace(state/'control.json')
        def fresh(data):return data.get('player_health',{}).get('progress_fresh') is True
        def check(label):report['checks'].append(label);print('PASS '+label,flush=True)
        def publish():
            run(['docker','rm','-f',publisher],check=False)
            run(['docker','run','-d','--name',publisher,'--network',network,image,'ffmpeg','-nostdin','-v','error',
                '-re','-f','lavfi','-i','testsrc2=size=320x180:rate=10','-an','-c:v','libx264',
                '-preset','ultrafast','-tune','zerolatency','-g','10','-f','rtsp','-rtsp_transport','tcp',
                'rtsp://stream-server:8554/camera'])
        try:
            for name in ('agent.py','cec_bridge.py','player_health.py'):shutil.copy(SOURCE/'pi'/name,root/name)
            (root/'Dockerfile').write_text('FROM debian:trixie-slim\n'
                'RUN apt-get update && apt-get install -y --no-install-recommends python3 mpv ffmpeg && rm -rf /var/lib/apt/lists/*\n'
                'WORKDIR /check\nCOPY *.py ./\n')
            run(['docker','build','-q','-t',image,str(root)],timeout=300)
            run(['docker','pull',SERVER_IMAGE],timeout=120)
            run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','1','-subj','/CN=stream-server',
                 '-addext','subjectAltName=DNS:stream-server','-keyout',str(cert/'server.key'),'-out',str(cert/'server.crt')])
            (cert/'server.key').chmod(0o600)
            configuration=root/'mediamtx.yml'
            configuration.write_text('logLevel: warn\nrtspTransports: [tcp]\nrtspEncryption: optional\n'
                'rtspServerKey: /cert/server.key\nrtspServerCert: /cert/server.crt\n'
                'rtmp: false\nhls: false\nwebrtc: false\nsrt: false\n'
                'paths:\n  camera:\n    source: publisher\n')
            (root/'consumer.py').write_text(CONSUMER)
            run(['docker','network','create','--internal',network])
            run(['docker','run','-d','--name',server,'--network',network,'--network-alias','stream-server',
                 '--mount','type=bind,src='+str(configuration)+',dst=/mediamtx.yml,readonly',
                 '--mount','type=bind,src='+str(cert)+',dst=/cert,readonly',SERVER_IMAGE])
            # Probe the actual TLS listener from the same private network.
            run(['docker','run','--rm','--network',network,image,'python3','-c',
                 "import socket,time;\nfor _ in range(40):\n try:\n  s=socket.create_connection(('stream-server',8322),timeout=1);s.close();break\n except OSError:time.sleep(.1)\nelse:raise RuntimeError('RTSPS listener missing')"])
            publish();command('on',1)
            run(['docker','run','-d','--name',consumer,'--network',network,
                 '--mount','type=bind,src='+str(state)+',dst=/state',
                 '--mount','type=bind,src='+str(root/'consumer.py')+',dst=/check/consumer.py,readonly',image,'python3','consumer.py'])
            first=wait_for(fresh,'initial RTSPS playback')
            deadline=first['deadline'];check('real TLS/RTSPS playback advances with video output')

            run(['docker','rm','-f',publisher])
            wait_for(lambda d:d.get('active') is True and not fresh(d),'camera publisher outage',20)
            check('camera publisher outage stops the fresh-playback indication')
            publish()
            recovered=wait_for(fresh,'recovery after camera publisher returns')
            assert recovered['deadline']==deadline and recovered['tv_commands']==['on 0\nas\n']
            check('camera stream returns automatically without repeated CEC or extended deadline')

            generation=recovered['generation']
            run(['docker','pause',server])
            wait_for(lambda d:d.get('active') is True and not fresh(d),'blackholed RTSPS stream',20)
            wait_for(lambda d:d.get('generation',0)>generation and not fresh(d),'retry during a silent connection stall',45)
            check('silent TLS connection stall causes bounded player retries')
            run(['docker','unpause',server]);publish()
            recovered=wait_for(fresh,'recovery after stalled server resumes')
            assert recovered['deadline']==deadline and recovered['tv_commands']==['on 0\nas\n']
            check('RTSPS recovery preserves automatic-off time and TV-command count')
            stable=wait_for(lambda d:d.get('player_health',{}).get('stable') is True,'stable recovery resets retry schedule',20)
            assert stable['retry_count']==0 and not stable['retry_scheduled']
            check('stable playback clears the previous failure backoff completely')

            run(['docker','stop','-t','2',server])
            wait_for(lambda d:d.get('active') is True and not fresh(d),'server restart outage',20)
            run(['docker','start',server]);publish()
            wait_for(fresh,'recovery after server restarts')
            check('full stream-server restart recovers automatically')

            command('switch_rtsp',2)
            wait_for(lambda d:d.get('sequence')==2 and fresh(d),'plain RTSP manual-source compatibility')
            check('manual RTSP stream also advances through the production player')
            command('menu',3)
            stopped=wait_for(lambda d:d.get('sequence')==3 and not d.get('active') and not d.get('player_running'),'return to menu')
            assert stopped['player_health']['state']=='stopped'
            check('return to menu stops video and recovery monitoring')
            command('on',4)
            wait_for(lambda d:d.get('sequence')==4 and fresh(d),'camera reopened')
            run(['docker','rm','-f',publisher])
            wait_for(lambda d:d.get('active') is True and not fresh(d),'camera outage before toggle-off',20)
            command('toggle',5)
            stopped=wait_for(lambda d:d.get('sequence')==5 and not d.get('active') and not d.get('player_running'),'toggle-off while camera unavailable')
            assert stopped['tv_commands'][-1]=='standby 0\n'
            check('toggle-off during camera outage stops recovery and requests TV standby')
            report['result']='passed'
            report['architecture']=run(['docker','image','inspect','--format','{{.Architecture}}',image]).stdout.strip()
            report['server_image']=SERVER_IMAGE
            report['player']=run(['docker','exec',consumer,'mpv','--version']).stdout.splitlines()[0]
            report['runtime_sha256']={name:hashlib.sha256((root/name).read_bytes()).hexdigest()
                for name in ('agent.py','cec_bridge.py','player_health.py')}
            print(json.dumps(report,indent=2),flush=True)
        except BaseException:
            for name in (server,publisher,consumer):
                logs=run(['docker','logs','--tail','20',name],check=False)
                print('TEST LOG '+name+'\n'+logs.stdout+logs.stderr,flush=True)
            raise
        finally:
            run(['docker','unpause',server],check=False)
            for name in (consumer,publisher,server):run(['docker','rm','-f',name],check=False)
            run(['docker','network','rm',network],check=False)
            run(['docker','image','rm',image],check=False)


if __name__=='__main__':main()
