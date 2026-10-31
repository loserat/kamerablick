"""Optional native mpv watchdog acceptance, without display/GPIO/CEC hardware."""
import json
from pathlib import Path
import secrets
import shutil
import subprocess
import tempfile

SOURCE=Path(__file__).resolve().parents[1]
PROBE='''import json,socket,subprocess,time
from pathlib import Path
from unittest.mock import patch
import agent

subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc=size=160x90:rate=10',
 '-t','40','-c:v','mpeg4','/tmp/video.avi'],check=True)
real_popen=subprocess.Popen
def headless(args,**kwargs):
 assert args[0]=='mpv'
 split=args.index('--')
 args=args[:split]+['--vo=null','--ao=null']+args[split:]
 return real_popen(args,**kwargs)
controller=agent.Controller('/tmp/kamerablick/config.json',clock=lambda:time.monotonic()*4)
controller.settings.update(stream_url='/tmp/video.avi',auto_off_minutes=1)
tv_commands=[]
controller.cec=tv_commands.append
def wait_for(predicate,seconds=8):
 deadline=time.monotonic()+seconds
 while time.monotonic()<deadline:
  controller.tick()
  if predicate():return
  time.sleep(.05)
 raise AssertionError('Native mpv condition did not arrive: '+str(controller.status()))
def pause():
 with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as s:
  s.settimeout(1);s.connect(str(controller.player_socket))
  s.sendall(b'{"command":["set_property","pause",true],"request_id":55}\\n')
  with s.makefile('rb') as response:
   for _ in range(100):
    event=json.loads(response.readline())
    if event.get('request_id')==55:
     assert event['error']=='success';return
  raise AssertionError('Pause not acknowledged')
checks=[]
with patch.object(agent.subprocess,'Popen',headless):
 try:
  controller.action('on')
  first=controller.player;deadline=controller.deadline
  wait_for(lambda:controller.health.snapshot()['progress_fresh'])
  assert controller.status()['player_running']
  assert oct(controller.player_socket.parent.stat().st_mode&0o777)=='0o700'
  checks.append('real mpv IPC reports advancing playback with video output')
  pause()
  wait_for(lambda:controller.player is None)
  assert first.poll() is not None and controller.want_on
  assert not controller.status()['player_health']['progress_fresh']
  checks.append('stalled playback is terminated even while process remains alive')
  wait_for(lambda:controller.player is not None and controller.health.snapshot()['progress_fresh'])
  assert controller.player.pid!=first.pid
  assert controller.deadline==deadline
  assert tv_commands==['on 0\\nas\\n']
  checks.append('new player recovers without repeating CEC or extending auto-off')
  socket_path=controller.player_socket
  controller.action('menu');controller.tick()
  assert not controller.want_on and controller.player is None
  assert not socket_path.exists()
  assert controller.health.snapshot()['state']=='stopped'
  checks.append('return to menu removes IPC socket and disables recovery')
 finally:controller.stop_player()
version=subprocess.run(['mpv','--version'],capture_output=True,text=True,check=True).stdout.splitlines()[0]
print(json.dumps({'result':'passed','scope':'Native mpv with local generated video and null video output; no RTSP, Protect, HDMI, GPIO or CEC hardware',
 'clock':'Watchdog clock runs 4x for acceptance; production thresholds unchanged','player':version,'checks':checks}))
'''


def main():
    image='kamerablick-player-acceptance:'+secrets.token_hex(6)
    try:
        with tempfile.TemporaryDirectory(prefix='kamerablick-player-') as directory:
            context=Path(directory)
            for name in ('agent.py','cec_bridge.py','player_health.py'):
                shutil.copy(SOURCE/'pi'/name,context/name)
            (context/'Dockerfile').write_text('FROM debian:trixie-slim\n'
                'RUN apt-get update && apt-get install -y --no-install-recommends python3 mpv ffmpeg && rm -rf /var/lib/apt/lists/*\n'
                'WORKDIR /check\nCOPY *.py ./\n')
            subprocess.run(['docker','build','-q','-t',image,str(context)],check=True,stdout=subprocess.DEVNULL)
            result=subprocess.run(['docker','run','--rm',image,'/usr/bin/python3','-c',PROBE],capture_output=True,text=True,timeout=40)
            if result.returncode:
                raise RuntimeError('Native Player-Abnahme fehlgeschlagen:\n'+result.stderr[-4000:])
            report=json.loads(result.stdout)
            report['architecture']=subprocess.run(['docker','image','inspect','--format','{{.Architecture}}',image],
                check=True,capture_output=True,text=True).stdout.strip()
            print(json.dumps(report,indent=2))
    finally:subprocess.run(['docker','image','rm',image],capture_output=True)


if __name__=='__main__':main()
