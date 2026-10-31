"""Read-only Pi preflight, then an explicit, idempotent installation as desktop user."""
import argparse
import ast
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import re
import secrets
import shlex
import shutil
import subprocess
import tempfile
import time

RUNTIME_FILES = ('agent.py', 'kiosk.py', 'session.py', 'cec_bridge.py', 'player_health.py')
MANAGED = '# Managed by Kamerablick installer\n'


def read_env(path):
    result = {}
    if not path.exists():
        return result
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if not re.fullmatch(r'[A-Z][A-Z0-9_]*=.*', line):
            raise ValueError('Die env-Datei enthält eine nicht unterstützte Zeile.')
        key, value = line.split('=', 1)
        if value.startswith(('"', "'")):
            values = shlex.split(value)
            if len(values) != 1:
                raise ValueError('Ungültiger env-Wert')
            value = values[0]
        result[key] = value
    return result


def atomic_write(path, data, mode=0o600):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix='.' + path.name, dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def runtime_release(root, source, names=None):
    names=tuple(RUNTIME_FILES if names is None else names)
    if not {'agent.py','kiosk.py','session.py'}.issubset(names) or not 3<=len(names)<=32 or len(set(names))!=len(names):
        raise ValueError('Unvollständige Pi-Laufzeit')
    digest = hashlib.sha256()
    files = {}
    for name in sorted(names):
        if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*[.]py',name):
            raise ValueError('Ungültiger Laufzeit-Dateiname')
        path=source/name
        if path.is_symlink() or not path.is_file() or path.stat().st_size>1024*1024:
            raise ValueError('Ungültige Laufzeit-Datei')
        text = path.read_text()
        ast.parse(text, filename=name)
        files[name] = text
        digest.update(name.encode() + b'\0' + text.encode())
    release = root / '.runtime/releases' / digest.hexdigest()[:20]
    release.mkdir(parents=True, exist_ok=True)
    for name, text in files.items():
        atomic_write(release / name, text)
    return release


def switch_runtime(root, release):
    root, release = root.resolve(), release.resolve()
    current = root / '.runtime/current'
    temporary = root / '.runtime/.current-next'
    temporary.unlink(missing_ok=True)
    temporary.symlink_to(os.path.relpath(release, current.parent))
    temporary.replace(current)


def managed_write(path, text, mode=0o644):
    if path.exists() and not path.read_text().startswith(MANAGED):
        raise ValueError('Vorhandene eigene Datei bleibt erhalten: ' + str(path))
    atomic_write(path, MANAGED + text, mode)


def registry_image(value):
    if not re.fullmatch(r'ghcr[.]io/[a-z0-9_.-]+/[a-z0-9_./-]+:v[0-9][A-Za-z0-9_.-]*',value):
        raise ValueError('Ein versioniertes GitHub-Image angeben: ghcr.io/besitzer/projekt:v1.0.0')
    return value


def run_command(args, *, capture=False, allowed=False):
    return subprocess.run(args,check=not allowed,capture_output=capture,text=True)


def extract_runtime(image, destination, runner=None):
    runner=runner or run_command
    container=runner(['docker','create',image],capture=True).stdout.strip()
    try:
        runner(['docker','cp',container+':/opt/kamerablick/pi',str(destination)],capture=True)
    finally:
        runner(['docker','rm',container],capture=True,allowed=True)
    source=Path(destination)
    if source.is_symlink() or not source.is_dir():
        raise ValueError('Image enthält keine gültige Pi-Laufzeit.')
    return source


def preflight(root):
    checks = []
    def add(name, passed, detail):
        checks.append({'name': name, 'ok': bool(passed), 'detail': detail})
    model_path = Path('/proc/device-tree/model')
    model = model_path.read_text().strip('\0\n') if model_path.exists() else 'Kein Pi erkannt'
    add('Raspberry Pi', platform.system() == 'Linux' and 'Raspberry Pi' in model, model)
    add('Prozessorarchitektur', platform.machine() in ('armv7l','armv8l','aarch64','arm64'), platform.machine()+'; ARMv7/32 Bit oder ARM64 erforderlich')
    add('Desktop-Benutzer', os.getuid() != 0, 'Als normaler Benutzer der grafischen Sitzung ausführen')
    for command in ('docker', 'systemctl', 'mpv', 'cec-client'):
        add(command, bool(shutil.which(command)), 'Erforderliches Programm')
    add('Chromium', bool(shutil.which('chromium') or shutil.which('chromium-browser')), 'TV-Browser')
    add('GPIO-Bibliothek', importlib.util.find_spec('gpiozero') is not None, 'python3-gpiozero')
    if shutil.which('docker'):
        for name, args in [('Docker erreichbar', ['info', '--format', '{{.OSType}}']), ('Compose', ['compose', 'version', '--short'])]:
            try:
                result = subprocess.run(['docker', *args], capture_output=True, text=True, timeout=10)
                add(name, result.returncode == 0, result.stdout.strip() if result.returncode == 0 else 'Docker-Dienst oder Benutzerrechte prüfen')
            except (OSError, subprocess.TimeoutExpired):
                add(name, False, 'Nicht erreichbar')
    add('Projektpfad', not any(c in str(root) for c in '\n\r%"'), 'Projektordner ohne Zeilenumbruch, Anführungszeichen oder Prozentzeichen')
    return checks


def prepare(root, home, image=None, runtime_source=None):
    root = root.resolve()
    env_path = root / '.env'
    settings = read_env(env_path)
    defaults = {'DASHBOARD_PASSWORD': secrets.token_urlsafe(24), 'AGENT_TOKEN': secrets.token_urlsafe(32),
        'DEMO_MODE': 'false', 'BIND': '0.0.0.0', 'PORT': '8088', 'AGENT_URL': 'http://127.0.0.1:8091', 'APP_VERSION': 'dev'}
    if image:
        defaults.update(OMA_TV_IMAGE=image,APP_VERSION=image.rsplit(':',1)[1])
    if env_path.exists():
        for key in ('DASHBOARD_PASSWORD', 'AGENT_TOKEN'):
            if not settings.get(key) or settings[key].startswith('BITTE_'):
                raise ValueError('Vorhandene .env zuerst mit echten lokalen Zugangswerten vervollständigen: ' + key)
        if settings.get('DEMO_MODE', 'true').lower() != 'false':
            raise ValueError('Vorhandene .env steht noch im Demomodus. DEMO_MODE bewusst auf false setzen.')
        if settings.get('HOME_TEST_MODE', 'false').lower() == 'true':
            raise ValueError('Vorhandene .env steht noch im Heimtest. Für den Pi-Echtbetrieb einen eigenen Installationsordner verwenden.')
        if image and (settings.get('OMA_TV_IMAGE')!=image or settings.get('APP_VERSION')!=defaults['APP_VERSION']):
            raise ValueError('Vorhandene Image-Version bleibt erhalten. Für einen Versionswechsel pi/update.sh verwenden.')
    settings = defaults | settings
    if not re.fullmatch(r'[A-Za-z0-9_-]{24,256}', settings['AGENT_TOKEN']):
        raise ValueError('AGENT_TOKEN: 24 bis 256 Buchstaben, Ziffern, Unterstrich oder Bindestrich verwenden')
    if settings['BIND'] not in ('127.0.0.1', '0.0.0.0'):
        raise ValueError('Dashboard-Bindung muss 127.0.0.1 (nur lokal) oder 0.0.0.0 (Heimnetz) sein.')
    if settings['AGENT_URL'] != 'http://127.0.0.1:8091':
        raise ValueError('Der interne Pi-Dienst muss ausschließlich lokal erreichbar bleiben.')
    if not settings['PORT'].isdigit() or not 1024 <= int(settings['PORT']) <= 65535:
        raise ValueError('PORT muss zwischen 1024 und 65535 liegen')
    for key, value in settings.items():
        if any(c in value for c in '\r\n\0'):
            raise ValueError('Ungültiger env-Wert: ' + key)
    config_dir = home / '.config/oma-tv'
    env_text = ''.join(key + '=' + value + '\n' for key, value in settings.items())
    user_units = home / '.config/systemd/user'
    desktop = home / '.config/autostart/kamerablick.desktop'
    agent_env = config_dir / 'agent.env'
    managed_paths = [agent_env, desktop, *[user_units / name for name in ('oma-tv-agent.service','oma-tv-kiosk.service','oma-tv-session.target')]]
    # Complete conflict check before any setting or service is changed.
    for path in managed_paths:
        if path.exists() and not path.read_text().startswith(MANAGED):
            raise ValueError('Eigene Datei vorhanden; wird nicht überschrieben: ' + str(path))
    source=runtime_source or root/'pi'
    names=None if runtime_source is None else sorted(path.name for path in source.glob('*.py'))
    release = runtime_release(root, source, names)
    if not env_path.exists():
        atomic_write(env_path, env_text)
    managed_write(agent_env, 'AGENT_TOKEN=' + settings['AGENT_TOKEN'] + '\nPORT=' + settings['PORT'] + '\nAGENT_CONFIG=' + str(config_dir / 'config.json') + '\n', mode=0o600)
    runtime = root / '.runtime/current'
    def service(description, script, restart):
        # systemd environment files handle literal paths without invoking a shell.
        return '[Unit]\nDescription=' + description + '\nPartOf=oma-tv-session.target\n\n[Service]\nEnvironmentFile="' + str(agent_env) + '"\nExecStart=/usr/bin/python3 "' + str(runtime / script) + '"\nRestart=' + restart + '\nRestartSec=5\nNoNewPrivileges=true\nTimeoutStopSec=15\n'
    managed_write(user_units / 'oma-tv-agent.service', service('Kamerablick Taster und TV', 'agent.py', 'on-failure'))
    managed_write(user_units / 'oma-tv-kiosk.service', service('Kamerablick TV Ansicht', 'kiosk.py', 'always'))
    managed_write(user_units / 'oma-tv-session.target', '[Unit]\nDescription=Kamerablick grafische Sitzung\nWants=oma-tv-agent.service oma-tv-kiosk.service\n')
    managed_write(desktop, '[Desktop Entry]\nType=Application\nName=Kamerablick\nExec=/usr/bin/python3 "' + str(runtime / 'session.py') + '"\nTerminal=false\n')
    switch_runtime(root, release)
    atomic_write(root / '.install.json', json.dumps({'schema': 1, 'root': str(root), 'home': str(home), 'runtime': str(release), 'agent_config': str(config_dir / 'config.json')}, indent=2) + '\n')
    return settings


def install_project(root, home, image=None):
    if image:
        run_command(['docker','pull',image])
        with tempfile.TemporaryDirectory(prefix='kamerablick-install-') as temporary:
            source=extract_runtime(image,Path(temporary)/'runtime')
            prepare(root,home,image=image,runtime_source=source)
        command=['docker','compose','up','-d','--wait','--wait-timeout','120','--no-build']
    else:
        prepare(root,home)
        command=['docker','compose','up','-d','--wait','--wait-timeout','120','--build']
    compose_env=dict(os.environ)
    compose_env.pop('OMA_TV_IMAGE',None);compose_env.pop('APP_VERSION',None)
    subprocess.run(command,cwd=root,env=compose_env,check=True)
    subprocess.run(['systemctl','--user','daemon-reload'],check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Nur lesen, nichts ändern')
    parser.add_argument('--install', action='store_true', help='Nach erfolgreicher Prüfung installieren')
    parser.add_argument('--image', type=registry_image, help='Fertiges GHCR-Image herunterladen; kein Containerbau auf dem Pi')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    image=args.image
    if not image:
        previous=read_env(root/'.env').get('OMA_TV_IMAGE','')
        if previous.startswith('ghcr.io/'):
            image=registry_image(previous)
    checks = preflight(root)
    for check in checks:
        print(('OK   ' if check['ok'] else 'FEHLT') + ' ' + check['name'] + ': ' + check['detail'])
    if not args.install:
        raise SystemExit(0 if all(c['ok'] for c in checks) else 1)
    if not all(c['ok'] for c in checks):
        raise SystemExit('Voraussetzungen fehlen. Es wurde nichts installiert.')
    try:
        install_project(root, Path.home(), image=image)
    except (ValueError, subprocess.CalledProcessError) as error:
        raise SystemExit('Installation nicht abgeschlossen. Voraussetzungen und Dateien prüfen. ' + (str(error) if isinstance(error, ValueError) else 'Dienststart fehlgeschlagen.'))
    print('Dateien eingerichtet. Bei der nächsten Desktop-Anmeldung startet Kamerablick automatisch.')
    print('Dashboard-Passwort steht ausschließlich in der lokalen .env. Protect im Dashboard einrichten.')
    installed = read_env(root / '.env')
    if installed['BIND'] == '0.0.0.0':
        print('Dashboard im Heimnetz: http://PI-IP:' + installed['PORT'] + ' (PI-IP durch die Adresse des Raspberry Pi ersetzen).')
    else:
        print('Dashboard nur lokal erreichbar; für den Browser einen SSH-Tunnel verwenden.')
    print('Keine Änderungen an Desktop-Autologin, SSH, VPN oder Router wurden vorgenommen.')


if __name__ == '__main__':
    main()
