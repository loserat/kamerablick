"""Update the container and host runtime together, with persistent rollback state."""
import argparse
import ast
import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time
import urllib.request

from install import atomic_write, read_env, runtime_release, switch_runtime, extract_runtime, project_root

ROOT = project_root(__file__)
SNAPSHOT = "import os,json,pathlib; p=pathlib.Path(os.getenv('DATA_DIR','/data')); print(json.dumps({f.name:f.read_text() for f in p.glob('*.json') if f.is_file() and not f.is_symlink()}))"
RESTORE = """import json,os,pathlib,tempfile,re
root=pathlib.Path(os.getenv('DATA_DIR','/data'))
data=json.load(__import__('sys').stdin)
for name,text in data.items():
    if not re.fullmatch(r'[A-Za-z0-9_-]+[.]json',name) or not isinstance(text,str): raise SystemExit('Ungültiges Backup')
    json.loads(text)
for name,text in data.items():
    fd,tmp=tempfile.mkstemp(dir=root)
    with os.fdopen(fd,'w') as f: f.write(text)
    os.chmod(tmp,0o600);os.replace(tmp,root/name)
for file in root.glob('*.json'):
    if file.name not in data and file.is_file() and not file.is_symlink(): file.unlink()
"""


def run(args, *, input=None, capture=False, allowed=False):
    env = dict(os.environ)
    # Image and application version must come from this installation's .env.
    env.pop('OMA_TV_IMAGE', None)
    env.pop('APP_VERSION', None)
    result = subprocess.run(args, cwd=ROOT, env=env, input=input, text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None, timeout=300)
    if result.returncode and not allowed:
        raise RuntimeError('Ein Wartungsschritt ist fehlgeschlagen: ' + args[0])
    return result


def compose(*args, **kwargs):
    return run(['docker', 'compose', *args], **kwargs)


def write_state(state):
    atomic_write(ROOT / 'backups/update-state.json', json.dumps(state, indent=2) + '\n')


def env_for_image(original, image, version=None):
    lines = [line for line in original.splitlines() if not line.startswith('OMA_TV_IMAGE=') and not (version and line.startswith('APP_VERSION='))]
    lines.append('OMA_TV_IMAGE=' + image)
    if version:
        lines.append('APP_VERSION=' + version)
    return '\n'.join(lines) + '\n'


def runtime_target():
    current = ROOT / '.runtime/current'
    if not current.is_symlink():
        raise RuntimeError('Zuerst die verwaltete Pi-Installation mit pi/install.py einrichten.')
    target = current.resolve()
    if not target.is_relative_to((ROOT / '.runtime/releases').resolve()):
        raise RuntimeError('Unbekannter Laufzeitpfad. Installation prüfen.')
    return target


def target_active():
    return run(['systemctl', '--user', 'is-active', '--quiet', 'oma-tv-session.target'], allowed=True, capture=True).returncode == 0


def maintenance_enabled():
    path=ROOT/'.install.json'
    return path.exists() and json.loads(path.read_text()).get('maintenance') is True


def restart_maintenance():
    if maintenance_enabled():
        run(['systemctl','--user','restart','oma-tv-maintenance.service'])


def wait_healthy(with_host):
    for _ in range(15):
        try:
            result = compose('exec', '-T', 'dashboard', 'python', '-c',
                "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:'+os.getenv('PORT','8088')+'/healthz',timeout=3)", allowed=True, capture=True)
            if result.returncode == 0:
                if maintenance_enabled():
                    env=read_env(ROOT/'.env')
                    req=urllib.request.Request('http://127.0.0.1:8093/status',headers={'Authorization':'Bearer '+env['AGENT_TOKEN']})
                    with urllib.request.urlopen(req,timeout=3) as response:
                        bridge=json.load(response)
                    if bridge.get('protocol')!=1 or bridge.get('runtime')!=runtime_target().name:
                        raise ValueError('Wartungsdienst noch nicht auf der gewählten Version')
                if not with_host:
                    return
                env = read_env(ROOT / '.env')
                req = urllib.request.Request('http://127.0.0.1:8091/action', data=b'{"action":"status"}',
                    headers={'Authorization': 'Bearer ' + env['AGENT_TOKEN'], 'Content-Type': 'application/json'})
                with urllib.request.urlopen(req, timeout=3) as response:
                    status = json.load(response)
                if 'gpio_pin' in status:
                    return
        except (OSError, ValueError, KeyError):
            pass
        time.sleep(2)
    raise RuntimeError('Startprüfung für Dashboard oder Pi-Dienst fehlgeschlagen.')


def rollback(state, progress=None):
    if progress: progress('rolling_back')
    backup = Path(state['backup'])
    print('Stelle vorherige Version und Einstellungen wieder her …', flush=True)
    if state['session_active']:
        run(['systemctl', '--user', 'stop', 'oma-tv-session.target'])
    original = (backup / 'environment').read_text()
    # Persist the actual old image, including on a later reboot.
    atomic_write(ROOT / '.env', env_for_image(original, state['rollback_image']))
    switch_runtime(ROOT, Path(state['previous_runtime']))
    compose('stop', 'dashboard', allowed=True)
    data = json.loads((backup / 'data.json').read_text())
    compose('run', '--rm', '-T', '--no-deps', 'dashboard', 'python', '-c', RESTORE, input=json.dumps(data), capture=True)
    host_backup = backup / 'host-config.json'
    manifest = json.loads((ROOT / '.install.json').read_text())
    if host_backup.exists():
        atomic_write(Path(manifest['agent_config']), host_backup.read_text())
    else:
        Path(manifest['agent_config']).unlink(missing_ok=True)
    compose('up', '-d', '--no-build')
    if state['session_active']:
        run(['systemctl', '--user', 'start', 'oma-tv-session.target'])
    restart_maintenance()
    wait_healthy(state['session_active'])
    state['phase'] = 'rolled_back'
    write_state(state)
    print('Vorherige Version wiederhergestellt und erreichbar.', flush=True)


def recover(progress=None):
    path = ROOT / 'backups/update-state.json'
    if not path.exists():
        return
    state = json.loads(path.read_text())
    if state.get('phase') in ('applying', 'rollback_failed'):
        rollback(state,progress)


def update(image, local=False, progress=None, verify=None):
    if not (ROOT / '.install.json').exists():
        raise RuntimeError('Verwaltete Installation fehlt. Zuerst pi/install.py --install ausführen.')
    previous_runtime = runtime_target()
    if progress: progress('downloading')
    if local:
        run(['docker', 'image', 'inspect', image], capture=True)
    else:
        run(['docker', 'pull', image])
    if verify:
        verify(image)
    with tempfile.TemporaryDirectory(prefix='kamerablick-update-') as temp:
        source=extract_runtime(image,Path(temp)/'runtime',runner=run)
        # Runtime modules belong to the selected image, not the old bootstrap.
        # This permits adding/removing helpers while switching versions together.
        names=sorted(path.name for path in source.glob('*.py'))
        release = runtime_release(ROOT, source, names)
    container = compose('ps', '-q', 'dashboard', capture=True).stdout.strip()
    if not container or '\n' in container:
        raise RuntimeError('Genau ein laufender Dashboard-Container wird erwartet.')
    actual_image = run(['docker', 'inspect', '--format', '{{.Image}}', container], capture=True).stdout.strip()
    stamp = time.strftime('%Y%m%d-%H%M%S') + '-' + str(os.getpid())
    if progress: progress('backing_up')
    rollback_image = 'oma-tv-rollback:' + stamp
    run(['docker', 'tag', actual_image, rollback_image])
    backup = ROOT / 'backups' / stamp
    backup.mkdir(parents=True, mode=0o700)
    backup.chmod(0o700)
    original = (ROOT / '.env').read_text()
    atomic_write(backup / 'environment', original)
    data = json.loads(compose('exec', '-T', 'dashboard', 'python', '-c', SNAPSHOT, capture=True).stdout)
    if not isinstance(data, dict):
        raise RuntimeError('Sicherung fehlgeschlagen.')
    atomic_write(backup / 'data.json', json.dumps(data))
    manifest = json.loads((ROOT / '.install.json').read_text())
    host_config = Path(manifest['agent_config'])
    if host_config.exists():
        atomic_write(backup / 'host-config.json', host_config.read_text())
    active = target_active()
    state = {'schema': 1, 'phase': 'applying', 'backup': str(backup), 'previous_runtime': str(previous_runtime),
        'rollback_image': rollback_image, 'session_active': active, 'new_image': image}
    write_state(state)
    try:
        if progress: progress('installing')
        if active:
            run(['systemctl', '--user', 'stop', 'oma-tv-session.target'])
        atomic_write(ROOT / '.env', env_for_image(original, image, image.rsplit(':',1)[-1]))
        switch_runtime(ROOT, release)
        compose('up', '-d', '--no-build')
        if active:
            run(['systemctl', '--user', 'start', 'oma-tv-session.target'])
        restart_maintenance()
        if progress: progress('verifying')
        wait_healthy(active)
    except (Exception, KeyboardInterrupt):
        try:
            rollback(state,progress)
        except Exception:
            state['phase'] = 'rollback_failed'
            write_state(state)
            raise RuntimeError('Wiederherstellung noch nicht abgeschlossen. pi/update.sh --recover ausführen.') from None
        raise RuntimeError('Neue Version nicht übernommen; vorherige Version ist wieder aktiv.') from None
    state['phase'] = 'complete'
    write_state(state)
    print('Container und Pi-Laufzeit aktualisiert. ' + ('Pi-Dienst erreichbar.' if active else 'Desktop war nicht aktiv; Pi-Dienst beim nächsten Login prüfen.'))
    print('Kamera, Taster und TV zusätzlich am Gerät prüfen.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('image', nargs='?')
    parser.add_argument('--local-image', help='Vorhandenes lokales Image für Abnahmeprüfungen')
    parser.add_argument('--recover', action='store_true')
    args = parser.parse_args()
    image = args.local_image or args.image
    if not args.recover:
        pattern = r'[a-z0-9][a-z0-9._/-]*:[A-Za-z0-9_][A-Za-z0-9_.-]*' if args.local_image else r'ghcr[.]io/[a-z0-9][a-z0-9._/-]*:v[0-9][A-Za-z0-9_.-]*'
        if not image or not re.fullmatch(pattern, image):
            raise SystemExit('Eine explizite Image-Version angeben, z. B. ghcr.io/besitzer/oma-tv:v1.0.0')
    os.umask(0o077)
    with open(ROOT / '.update.lock','a') as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit('Ein Update läuft bereits. Bitte warten.')
        try:
            recover()
            if not args.recover:
                update(image, bool(args.local_image))
        except Exception as error:
            raise SystemExit(str(error)) from None


if __name__ == '__main__':
    main()
