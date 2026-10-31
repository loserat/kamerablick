"""Local Docker acceptance; optional ARMv7 emulation, no target Pi or Protect."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import tempfile
import time

SOURCE=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--platform',default='linux/arm64',choices=('linux/arm64','linux/arm/v7','linux/amd64'))
args=parser.parse_args()
case=Path(tempfile.mkdtemp(prefix='kamerablick-docker-acceptance-'))
instance=secrets.token_hex(6)
image='kamerablick-acceptance:'+instance
upgraded_image='kamerablick-acceptance:new-'+instance
bad_image='kamerablick-acceptance:bad-'+instance
root=case/'project';fakehome=case/'home'
shutil.copytree(SOURCE,root,ignore=shutil.ignore_patterns('__pycache__','.env','.runtime','.install.json','data','backups','.update.lock'))
sys.path.insert(0,str(root/'pi'))
import install
# Reference host runtime deliberately differs from the new image.
with (root/'pi/agent.py').open('a') as f:f.write('\n# acceptance reference runtime\n')
install.prepare(root,fakehome)
reference_runtime=(root/'.runtime/current').resolve()
text=(root/'.env').read_text().replace('DEMO_MODE=false','DEMO_MODE=true').replace('PORT=8088','PORT=18878')
text+='OMA_TV_IMAGE='+image+'\n'
(root/'.env').write_text(text)
binpath=case/'bin';binpath.mkdir()
(binpath/'systemctl').write_text('#!/bin/sh\nexit 3\n');(binpath/'systemctl').chmod(0o755)
env=os.environ|{'COMPOSE_PROJECT_NAME':'kamerablick_goal_'+secrets.token_hex(4),'PATH':str(binpath)+os.pathsep+os.environ['PATH'],'DOCKER_DEFAULT_PLATFORM':args.platform}
report={'scope':'Local Docker demo; no Pi, GPIO, CEC, real camera or VPN.','checks':[]}

def run(args,*,input=None,ok=True):
    p=subprocess.run(args,cwd=root,env=env,input=input,text=True,capture_output=True,timeout=240)
    if ok and p.returncode:
        raise RuntimeError('Command failed: '+args[0]+'\n'+p.stdout[-2500:]+'\n'+p.stderr[-2500:])
    return p

def compose(*args,**kwargs):return run(['docker','compose',*args],**kwargs)
def wait_dashboard():
    for _ in range(30):
        p=compose('exec','-T','dashboard','python','-c',"import os,urllib.request;urllib.request.urlopen('http://127.0.0.1:'+os.getenv('PORT')+'/healthz',timeout=2)",ok=False)
        if p.returncode==0:return True
        time.sleep(1)
    return False
def check(name,passed):
    if not passed:raise AssertionError(name)
    report['checks'].append(name);print('PASS '+name,flush=True)

API="""import os,json,urllib.request,urllib.error,hashlib,struct
base='http://127.0.0.1:'+os.getenv('PORT')
def call(path,data=None,token=''):
 r=urllib.request.Request(base+'/api/'+path,data=json.dumps(data).encode() if data is not None else None,headers={'Content-Type':'application/json','Authorization':'Bearer '+token})
 with urllib.request.urlopen(r,timeout=8) as response:return json.load(response)
admin=call('login',{'password':os.getenv('DASHBOARD_PASSWORD')})['token']
provision=call('tv/provision',{},os.getenv('AGENT_TOKEN'))
access=provision['token']
receiver=provision['receiver']
assert receiver!=access
assert 'receiver' not in call('tv/pair',{},admin)
try:call('tv/input',{'client':'acceptance-browser'},access);raise AssertionError('TV access allowed CEC receiver')
except urllib.error.HTTPError as e:assert e.code==401
assert call('tv/input',{'client':'acceptance-browser'},receiver)['events']==[]
try:call('config',{'gpio_pin':18},access);raise AssertionError('TV allowed configuration')
except urllib.error.HTTPError as e:assert e.code==401
status=call('status',token=admin)
print(json.dumps({'camera_name':status['config']['camera_name'],'gpio':status['config']['gpio_pin'],'access_digest':hashlib.sha256(access.encode()).hexdigest(),'receiver_digest':hashlib.sha256(receiver.encode()).hexdigest(),'version':status['version'],'pointer_bits':struct.calcsize('P')*8}))
"""
try:
    run(['docker','build','--platform',args.platform,'-t',image,str(SOURCE)])
    report['requested_platform']=args.platform
    report['image_architecture']=run(['docker','image','inspect','--format','{{.Architecture}}',image]).stdout.strip()
    compose('up','-d','--no-build')
    check('actual container health endpoint',wait_dashboard())
    seed=API.replace("status=call('status',token=admin)","call('config',{'camera_name':'Abnahmekamera','gpio_pin':17,'stream_url':'rtsps://127.0.0.1/test-only'},admin)\nstatus=call('status',token=admin)")
    initial=json.loads(compose('exec','-T','dashboard','python','-',input=seed).stdout)
    report['container_pointer_bits']=initial['pointer_bits']
    check('requested container userspace architecture',initial['pointer_bits']==(32 if args.platform=='linux/arm/v7' else 64))
    check('HTTP login, persistent config and restricted TV provisioning',initial['camera_name']=='Abnahmekamera')
    compose('restart','dashboard')
    assert wait_dashboard(),'dashboard not ready after restart'
    restarted=json.loads(compose('exec','-T','dashboard','python','-',input=API).stdout)
    check('container restart preserves settings and TV pairing',restarted['camera_name']==initial['camera_name'] and restarted['access_digest']==initial['access_digest'] and restarted['receiver_digest']==initial['receiver_digest'])
    upgraded=case/'upgraded';upgraded.mkdir()
    (upgraded/'Dockerfile').write_text('FROM '+image+'\nUSER root\nRUN echo VALUE=42 > /opt/kamerablick/pi/future_helper.py\nUSER app\n')
    run(['docker','build','-t',upgraded_image,str(upgraded)])
    run([sys.executable,'pi/update.py','--local-image',upgraded_image])
    updated=json.loads(compose('exec','-T','dashboard','python','-',input=API).stdout)
    check('coordinated update switches host runtime and application version',(root/'.runtime/current').resolve()!=reference_runtime and updated['version']=='new-'+instance)
    check('update receives additional host modules from the selected image', 'VALUE=42' in (root/'.runtime/current/future_helper.py').read_text())
    bad=case/'bad';bad.mkdir()
    (bad/'Dockerfile').write_text('FROM '+upgraded_image+'\nCMD ["python", "-c", "from pathlib import Path; import time; Path(\'/data/config.json\').write_text(\'{}\'); time.sleep(600)"]\n')
    run(['docker','build','-t',bad_image,str(bad)])
    failed=run([sys.executable,'pi/update.py','--local-image',bad_image],ok=False)
    state=json.loads((root/'backups/update-state.json').read_text())
    restored=json.loads(compose('exec','-T','dashboard','python','-',input=API).stdout)
    check('unhealthy image triggers automatic rollback',failed.returncode!=0 and state['phase']=='rolled_back')
    check('rollback restores mutated data and paired TV access',restored['camera_name']==updated['camera_name'] and restored['access_digest']==updated['access_digest'] and restored['receiver_digest']==updated['receiver_digest'])
    check('rollback image remains selected after later restart','OMA_TV_IMAGE=oma-tv-rollback:' in (root/'.env').read_text())
    compose('restart','dashboard')
    assert wait_dashboard(),'rollback not ready after restart'
    final=json.loads(compose('exec','-T','dashboard','python','-',input=API).stdout)
    check('restarted rollback stays functional',final['camera_name']=='Abnahmekamera')
    # Exercise the same persistent recovery record used by the desktop autostart.
    state['phase']='applying';install.atomic_write(root/'backups/update-state.json',json.dumps(state))
    run([sys.executable,'pi/update.py','--recover'])
    check('interrupted-update recovery completes on the next invocation',json.loads((root/'backups/update-state.json').read_text())['phase']=='rolled_back')
    report['result']='passed'
finally:
    compose('down','--volumes',ok=False)
    for backup in (root/'backups').glob('*') if (root/'backups').exists() else []:
        if backup.is_dir(): run(['docker','image','rm','oma-tv-rollback:'+backup.name],ok=False)
    for test_image in (bad_image,upgraded_image,image): run(['docker','image','rm',test_image],ok=False)
    print(json.dumps(report,indent=2))
    shutil.rmtree(case)
