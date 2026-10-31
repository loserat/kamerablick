"""Optional native ARM64/Linux CEC-process check in an isolated Docker container."""
import json
from pathlib import Path
import secrets
import shutil
import subprocess
import tempfile

SOURCE = Path(__file__).resolve().parents[1]
PROBE = '''import subprocess,time,json
from cec_bridge import CecBridge,RemoteInput
info=subprocess.run(['cec-client','-i'],capture_output=True,text=True,timeout=5)
assert info.returncode==0
direct=subprocess.run(['cec-client','-d','13','-t','p','-o','Kamerablick','-aw','0'],input='',capture_output=True,text=True,timeout=10)
assert direct.returncode!=0
assert 'failed' in (direct.stdout+direct.stderr).lower()
assert 'skipped' not in (direct.stdout+direct.stderr).lower()
assert 'disabling auto-wake' in direct.stdout.lower()
b=CecBridge(RemoteInput());b.start()
time.sleep(2)
assert not b.snapshot()['connected']
try:b.command('on')
except RuntimeError:pass
else:raise AssertionError('Missing adapter was reported as connected')
b.close()
assert not b.thread.is_alive() and b.process is None
print(json.dumps({'scope':'Native Debian Trixie cec-client without attached CEC/GPIO hardware',
 'result':'passed','library':info.stdout.strip(),
 'checks':['CLI options accepted','missing adapter never reported connected','command rejected without adapter','service thread and helper stop cleanly']}))
'''


def main():
    image = 'kamerablick-cec-acceptance:' + secrets.token_hex(6)
    try:
        with tempfile.TemporaryDirectory(prefix='kamerablick-cec-') as directory:
            context = Path(directory)
            shutil.copy(SOURCE / 'pi/cec_bridge.py', context / 'cec_bridge.py')
            (context / 'Dockerfile').write_text('FROM debian:trixie-slim\n'
                'RUN apt-get update && apt-get install -y --no-install-recommends python3 cec-utils && rm -rf /var/lib/apt/lists/*\n'
                'WORKDIR /check\nCOPY cec_bridge.py ./\n')
            subprocess.run(['docker', 'build', '-q', '-t', image, str(context)], check=True, stdout=subprocess.DEVNULL)
            result = subprocess.run(['docker', 'run', '--rm', image, '/usr/bin/python3', '-c', PROBE],
                                    check=True, capture_output=True, text=True, timeout=20)
            report = json.loads(result.stdout)
            report['architecture'] = subprocess.run(['docker', 'image', 'inspect', '--format', '{{.Architecture}}', image],
                check=True, capture_output=True, text=True).stdout.strip()
            print(json.dumps(report, indent=2))
    finally:
        subprocess.run(['docker', 'image', 'rm', image], capture_output=True)


if __name__ == '__main__': main()
