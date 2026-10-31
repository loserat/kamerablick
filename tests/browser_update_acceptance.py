"""Docker browser-update lab; transport/systemd stand-ins, no Pi or real releases."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import tempfile
import time

SOURCE=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--interactive',action='store_true',help='Wait for a browser test before continuing automatic failure tests')
parser.add_argument('--control',type=Path,help='Directory for lab metadata and the continue marker')
args=parser.parse_args()
case=Path(tempfile.mkdtemp(prefix='kamerablick-browser-update-'))
instance=secrets.token_hex(5)
base='kamerablick-browser-lab:'+instance
host_image='kamerablick-update-host:'+instance
host='kamerablick-update-host-'+instance
shim='kamerablick-update-shim-'+instance
project='kamerablick_update_'+instance
versions=['v9.9.90','v9.9.91','v9.9.92']
images=['ghcr.io/loserat/kamerablick:'+tag for tag in versions]
report={'scope':'Actual Docker images, HTTP UI/API, detached processes and rollback; GitHub/download transport and systemd are stand-ins. No Pi, GPIO, TV or real public test releases.','checks':[]}

SHIM=r'''
import sys
from pathlib import Path
runtime=Path('/fixture/project/.runtime/current')
sys.path.insert(0,str(runtime if runtime.exists() else Path('/fixture/project/pi') if Path('/fixture/project/pi').exists() else Path('/opt/kamerablick/pi')))
import release_info
def release(tag=None,refresh=False):
 value=tag or (Path(__file__).parent/'latest').read_text().strip()
 release_info.version(value)
 return {'version':value,'name':'Testrelease '+value,'notes':'Lokales Update-Testlabor. Keine echte GitHub-Veröffentlichung.','url':'https://github.com/loserat/kamerablick/releases/tag/'+value,'published_at':None}
release_info.release=release
'''
DOCKER_WRAPPER=r'''#!/usr/local/bin/python
import os,sys
if sys.argv[1:2]==['pull'] and sys.argv[-1] in ['ghcr.io/loserat/kamerablick:v9.9.90','ghcr.io/loserat/kamerablick:v9.9.91','ghcr.io/loserat/kamerablick:v9.9.92']:
 raise SystemExit(0)
os.execv('/usr/bin/docker',['docker',*sys.argv[1:]])
'''
SYSTEMD_RUN=r'''#!/usr/local/bin/python
import json,os,subprocess,sys
from pathlib import Path
unit=next(arg.split('=',1)[1] for arg in sys.argv if arg.startswith('--unit='))
start=sys.argv.index('/usr/bin/python3')
command=sys.argv[start:];command[0]='/usr/local/bin/python'
log=open('/fixture/worker.log','ab')
process=subprocess.Popen(command,start_new_session=True,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT)
Path('/fixture/units').mkdir(exist_ok=True)
Path('/fixture/units',unit).write_text(str(process.pid))
'''
SYSTEMCTL=r'''#!/usr/local/bin/python
import os,sys,time
from pathlib import Path
args=sys.argv[1:]
if 'is-active' in args:raise SystemExit(3)
if 'show' in args:
 if '--property=LoadState' in args:
  print('loaded');raise SystemExit(0)
 unit=args[args.index('show')+1]
 try:
  pid=int(Path('/fixture/units',unit).read_text());state=Path('/proc',str(pid),'stat').read_text().split()[2]
  print('inactive' if state=='Z' else 'active')
 except (OSError,ValueError):print('inactive')
 raise SystemExit(0)
if 'restart' in args and 'oma-tv-maintenance.service' in args:
 marker=Path('/fixture/restart');marker.write_text('restart')
 for _ in range(100):
  if not marker.exists():raise SystemExit(0)
  time.sleep(.1)
 raise SystemExit(1)
raise SystemExit(0)
'''
SUPERVISOR=r'''
import json,os,secrets,subprocess,sys,threading,time
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
sys.path.insert(0,'/fixture/project/pi')
import install
root=Path('/fixture/project');home=Path('/fixture/home')
settings=install.prepare(root,home,image='ghcr.io/loserat/kamerablick:v9.9.90')
p=root/'.env';s=p.read_text().replace('PORT=8088','PORT=18879').replace(settings['DASHBOARD_PASSWORD'],'browser-lab')
s+='COMPOSE_PROJECT_NAME='+os.environ['LAB_PROJECT']+'\n';p.write_text(s)
manifest=json.loads((root/'.install.json').read_text());manifest['maintenance']=True;(root/'.install.json').write_text(json.dumps(manifest))
compose=root/'compose.yaml';s=compose.read_text().replace('network_mode: host','network_mode: "container:'+os.environ['LAB_HOST']+'"')
s=s.replace('DATA_DIR: /data','DATA_DIR: /data\n      PYTHONPATH: /testshim:/opt/kamerablick/pi')
s=s.replace('- settings:/data','- settings:/data\n      - fixture_shim:/testshim:ro')
s+='  fixture_shim:\n    external: true\n    name: '+os.environ['LAB_SHIM']+'\n';compose.write_text(s)
Path('/fixture/shim/latest').write_text('v9.9.91')
class Agent(BaseHTTPRequestHandler):
 def log_message(self,*a):pass
 def do_POST(self):
  length=int(self.headers.get('Content-Length',0));self.rfile.read(length)
  raw=json.dumps({'gpio_pin':17,'active':False,'tv':'Testlabor','message':'Testlabor ohne GPIO oder TV'}).encode()
  self.send_response(200);self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
threading.Thread(target=ThreadingHTTPServer(('127.0.0.1',8091),Agent).serve_forever,daemon=True).start()
def launch():
 env=os.environ|{'AGENT_TOKEN':settings['AGENT_TOKEN']}
 return subprocess.Popen(['/usr/local/bin/python',str(root/'.runtime/current/maintenance.py'),'--root',str(root)],env=env)
broker=launch()
subprocess.run(['docker','compose','up','-d','--no-build'],cwd=root,check=True)
Path('/fixture/ready').write_text('ready')
while True:
 if Path('/fixture/restart').exists():
  broker.terminate();broker.wait(timeout=5);broker=launch();Path('/fixture/restart').unlink()
 time.sleep(.1)
'''
API=r'''
import json,urllib.request,urllib.error
base='http://127.0.0.1:18879'
def call(path,body=None,token=None):
 headers={'Content-Type':'application/json'}
 if token:headers['Authorization']='Bearer '+token
 req=urllib.request.Request(base+'/api/'+path,data=json.dumps(body).encode() if body is not None else None,headers=headers)
 with urllib.request.urlopen(req,timeout=20) as response:return json.load(response)
admin=call('login',{'password':'browser-lab'})['token']
'''

def run(command,*,ok=True,timeout=300):
 result=subprocess.run(command,text=True,capture_output=True,timeout=timeout)
 if ok and result.returncode:raise RuntimeError('Lab command failed: '+command[0]+'\n'+result.stdout[-3000:]+'\n'+result.stderr[-3000:])
 return result

def inside(code,ok=True):return run(['docker','exec','-i',host,'python','-c',code],ok=ok)
def api(code):return json.loads(inside(API+code).stdout)
def check(label):report['checks'].append(label);print('PASS '+label,flush=True)
def wait_job(watch,expected):
 for _ in range(100):
  result=inside("import json,urllib.request\nreq=urllib.request.Request('http://127.0.0.1:18879/api/update/progress',data=json.dumps({'watch':"+repr(watch)+"}).encode(),headers={'Content-Type':'application/json'})\nwith urllib.request.urlopen(req,timeout=5) as response:print(response.read().decode())",ok=False)
  if result.returncode==0:
   data=json.loads(result.stdout);phase=(data.get('job') or {}).get('phase')
   if phase in ('complete','rolled_back','failed','recovery_failed'):
    assert phase==expected,(phase,expected);return data
  time.sleep(1)
 raise AssertionError('Update did not finish')

for image in images:
 if run(['docker','image','inspect',image],ok=False).returncode==0:
  shutil.rmtree(case)
  raise SystemExit('Reserved test image already exists; refusing to overwrite it: '+image)

try:
 run(['docker','build','-t',base,str(SOURCE)])
 build=case/'host';build.mkdir();shutil.copytree(SOURCE/'pi',build/'pi');shutil.copy(SOURCE/'compose.yaml',build/'compose.yaml')
 (build/'bin').mkdir();(build/'shim').mkdir()
 for name,text in [('docker',DOCKER_WRAPPER),('systemd-run',SYSTEMD_RUN),('systemctl',SYSTEMCTL),('loginctl','#!/bin/sh\necho yes\n')]:
  p=build/'bin'/name;p.write_text(text);p.chmod(0o755)
 (build/'shim/sitecustomize.py').write_text(SHIM);(build/'shim/latest').write_text('v9.9.91')
 (build/'supervisor.py').write_text(SUPERVISOR)
 (build/'Dockerfile').write_text('FROM python:3.13-slim\nRUN apt-get update && apt-get install -y --no-install-recommends docker.io docker-cli docker-compose && rm -rf /var/lib/apt/lists/*\nCOPY pi/ /fixture/project/pi/\nCOPY compose.yaml /fixture/project/compose.yaml\nCOPY bin/ /fixture/bin/\nCOPY shim/ /fixture/shim/\nCOPY supervisor.py /fixture/supervisor.py\nENV PATH=/fixture/bin:/usr/local/bin:/usr/bin:/bin PYTHONPATH=/fixture/shim\nCMD ["python","/fixture/supervisor.py"]\n')
 run(['docker','build','-t',host_image,str(build)])
 for index,(tag,image) in enumerate(zip(versions,images)):
  context=case/tag;context.mkdir()
  content='FROM '+base+'\nLABEL org.opencontainers.image.source=https://github.com/loserat/kamerablick org.opencontainers.image.version='+tag+'\n'
  if index==1:content+='USER root\nRUN echo VALUE=42 > /opt/kamerablick/pi/browser_future_helper.py\nUSER app\n'
  if index==2:content+='CMD ["python","-c","from pathlib import Path; import time; Path(\'/data/config.json\').write_text(\'{}\'); time.sleep(600)"]\n'
  (context/'Dockerfile').write_text(content);run(['docker','build','-t',image,str(context)])
 run(['docker','run','-d','--name',host,'-v','/var/run/docker.sock:/var/run/docker.sock','-v',shim+':/fixture/shim','-e','LAB_HOST='+host,'-e','LAB_SHIM='+shim,'-e','LAB_PROJECT='+project,'-p','127.0.0.1::18879',host_image])
 for _ in range(120):
  if run(['docker','inspect','--format','{{.State.Running}}',host],ok=False).stdout.strip()!='true':raise AssertionError('Lab host exited during startup')
  if inside("from pathlib import Path;raise SystemExit(0 if Path('/fixture/ready').exists() else 1)",ok=False).returncode==0:break
  time.sleep(1)
 else:raise AssertionError('Lab host did not become ready')
 for _ in range(30):
  result=inside(API+"print(json.dumps(call('status',token=admin)))",ok=False)
  if result.returncode==0:break
  time.sleep(1)
 else:raise AssertionError('Dashboard not ready')
 status=json.loads(result.stdout);assert status['maintenance']['available'] and status['maintenance']['persistent']
 seed=api("call('config',{'camera_name':'Testkamera','stream_url':'rtsps://192.0.2.1/test-stream'},admin)\npair=call('tv/pair',{},admin)\nprint(json.dumps({'access':pair['token'],'version':call('status',token=admin)['version']}))")
 inside("from pathlib import Path;import subprocess\ncode=\"import server;server.save('protect.json',{'api_key':'test-private-key'})\"\nsubprocess.run(['docker','compose','exec','-T','dashboard','python','-c',code],cwd='/fixture/project',check=True)")
 check('real dashboard, maintenance bridge and private settings initialized')
 details=api("print(json.dumps(call('update',token=admin)))");assert details['can_install'] and details['version']=='v9.9.91'
 if args.interactive:
  control=(args.control or case/'control').resolve();control.mkdir(parents=True,exist_ok=True)
  address=run(['docker','port',host,'18879/tcp']).stdout.strip()
  (control/'lab.json').write_text(json.dumps({'url':'http://'+address+'/#maintenance','password':'browser-lab','continue':str(control/'continue')}))
  print('BROWSER_READY '+str(control/'lab.json'),flush=True)
  for _ in range(1800):
   if (control/'continue').exists():break
   time.sleep(1)
  else:raise AssertionError('Browser test was not continued')
  job=json.loads(inside("from pathlib import Path;print(Path('/fixture/project/.maintenance/job.json').read_text())").stdout)
  assert job['phase']=='complete'
 else:
  started=api("print(json.dumps(call('update/install',{'version':'v9.9.91','confirm':True},admin)))");wait_job(started['watch'],'complete')
 after=api("print(json.dumps(call('status',token=admin)))")
 assert after['version']=='v9.9.91' and after['config']['camera_name']=='Testkamera'
 inside("from pathlib import Path;assert 'VALUE=42' in Path('/fixture/project/.runtime/current/browser_future_helper.py').read_text()")
 assert api("print(json.dumps(call('tv/pair',{},admin)))")['token']==seed['access']
 check('browser update switches dashboard and host runtime while preserving camera and TV access')
 mounts=json.loads(inside("import subprocess,json\nc=subprocess.check_output(['docker','compose','ps','-q','dashboard'],cwd='/fixture/project',text=True).strip()\nprint(subprocess.check_output(['docker','inspect','--format','{{json .Mounts}}',c],text=True))").stdout)
 assert not any('docker.sock' in m['Destination'] for m in mounts)
 check('dashboard has no Docker socket during the update')
 inside("from pathlib import Path;Path('/fixture/shim/latest').write_text('v9.9.92')")
 started=api("print(json.dumps(call('update/install',{'version':'v9.9.92','confirm':True},admin)))")
 wait_job(started['watch'],'rolled_back')
 restored=api("print(json.dumps(call('status',token=admin)))")
 assert restored['version']=='v9.9.91' and restored['config']['camera_name']=='Testkamera'
 assert api("print(json.dumps(call('tv/pair',{},admin)))")['token']==seed['access']
 inside("import subprocess\ncode=\"import server;assert server.credentials()['api_key']=='test-private-key'\"\nsubprocess.run(['docker','compose','exec','-T','dashboard','python','-c',code],cwd='/fixture/project',check=True)")
 check('bad image rolls back dashboard, host runtime, camera, private credentials and TV access')
 inside("from pathlib import Path;import json\np=Path('/fixture/project/backups/update-state.json');d=json.loads(p.read_text());d['phase']='applying';p.write_text(json.dumps(d))\np=Path('/fixture/project/.maintenance/job.json');d=json.loads(p.read_text());d['phase']='verifying';p.write_text(json.dumps(d))\nPath('/fixture/restart').write_text('restart')")
 wait_job(started['watch'],'rolled_back')
 check('interrupted transaction is recovered by the independent maintenance bridge')
 inside("from pathlib import Path;import json\np=Path('/fixture/project/backups/update-state.json');d=json.loads(p.read_text());d['phase']='rollback_failed';p.write_text(json.dumps(d))\np=Path('/fixture/project/.maintenance/job.json');d=json.loads(p.read_text());d.update(phase='recovery_failed',recovery_attempts=1);p.write_text(json.dumps(d))")
 inside("import sys\nfrom pathlib import Path\nsys.path.insert(0,'/fixture/project/pi')\nimport reinstall,install\ninstall.preflight=lambda root:[{'ok':True}]\nbackup=reinstall.reinstall(Path('/fixture/project'),Path('/fixture/home'),'ghcr.io/loserat/kamerablick:v9.9.91')\nassert (backup/'previous-update-state.json').exists()\nassert (backup/'previous-job.json').exists()")
 restored=api("print(json.dumps(call('status',token=admin)))")
 assert restored['version']=='v9.9.91' and restored['config']['camera_name']=='Testkamera'
 assert restored['maintenance']['available'] and restored['maintenance']['persistent']
 assert api("print(json.dumps(call('tv/pair',{},admin)))")['token']==seed['access']
 inside("import subprocess\ncode=\"import server;assert server.credentials()['api_key']=='test-private-key'\"\nsubprocess.run(['docker','compose','exec','-T','dashboard','python','-c',code],cwd='/fixture/project',check=True)")
 check('cold reinstall archives interrupted transaction and preserves camera, private credentials and TV access')
 report['result']='passed'
finally:
 logs=run(['docker','logs',host],ok=False).stdout
 if report.get('result')!='passed' and logs:print(logs[-5000:],flush=True)
 backups=inside("from pathlib import Path;import json;print(json.dumps([p.name for p in Path('/fixture/project/backups').glob('*') if p.is_dir()]))",ok=False)
 retained=inside("from pathlib import Path;import json;print(json.dumps([json.loads(p.read_text())['retained_image'] for p in Path('/fixture/project/backups').glob('neuinstallation-*/reinstall.json')]))",ok=False)
 inside("import subprocess;subprocess.run(['docker','compose','down','--volumes','--timeout','5'],cwd='/fixture/project')",ok=False)
 run(['docker','rm','-f',host],ok=False);run(['docker','volume','rm',shim],ok=False)
 if backups.returncode==0:
  for stamp in json.loads(backups.stdout):run(['docker','image','rm','oma-tv-rollback:'+stamp],ok=False)
 if retained.returncode==0:
  for image in json.loads(retained.stdout):run(['docker','image','rm',image],ok=False)
 for image in [*images,host_image,base]:run(['docker','image','rm',image],ok=False)
 print(json.dumps(report,indent=2),flush=True)
 if args.control:
  args.control.mkdir(parents=True,exist_ok=True);(args.control/'result.json').write_text(json.dumps(report,indent=2)+'\n')
 shutil.rmtree(case)
