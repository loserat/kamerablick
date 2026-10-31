"""Reinstall a managed Pi without deleting its settings volume or recovery evidence."""
import argparse
import fcntl
import json
from pathlib import Path
import secrets
import shutil
import subprocess
import tempfile
import time

import install
import release_info
import update
from update_job import verify_image

UNITS = ('oma-tv-session.target', 'oma-tv-agent.service', 'oma-tv-kiosk.service', 'oma-tv-maintenance.service')


def reinstall(root, home, image):
    root, home = Path(root).resolve(), Path(home).resolve()
    if not image.startswith(release_info.IMAGE + ':'):
        raise ValueError('Das offizielle versionierte Kamerablick-Image verwenden.')
    tag = image.rsplit(':', 1)[1]
    release_info.version(tag)
    manifest_path = root / '.install.json'
    if not manifest_path.is_file():
        raise ValueError('Verwaltete Installation fehlt. pi/install.py verwenden.')
    manifest = json.loads(manifest_path.read_text())
    if Path(manifest['root']).resolve() != root or Path(manifest['home']).resolve() != home:
        raise ValueError('Installationsordner und Desktop-Benutzer müssen zur bisherigen Installation passen.')
    if not all(check['ok'] for check in install.preflight(root)):
        raise ValueError('Voraussetzungen prüfen: python3 pi/install.py --check')
    settings = install.read_env(root / '.env')
    if settings.get('DEMO_MODE', 'true').lower() != 'false' or settings.get('HOME_TEST_MODE', 'false').lower() == 'true':
        raise ValueError('Nur für eine vorhandene Pi-Installation im Echtbetrieb vorgesehen.')
    owned = [home / '.config/oma-tv/agent.env', home / '.config/autostart/kamerablick.desktop',
        *(home / '.config/systemd/user' / name for name in UNITS)]
    for path in owned:
        if path.exists() and not path.read_text().startswith(install.MANAGED):
            raise ValueError('Eigene Datei bleibt erhalten; zuerst prüfen: ' + str(path))
    previous_root = update.ROOT
    update.ROOT = root
    backup = None
    try:
        with open(root / '.update.lock', 'a') as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise ValueError('Ein Update oder eine Installation läuft noch.') from None
            # All download and provenance checks precede changes to the installation.
            release_info.release(tag, refresh=True)
            update.run(['docker', 'pull', image])
            verify_image(image)
            with tempfile.TemporaryDirectory(prefix='kamerablick-reinstall-') as temporary:
                source = install.extract_runtime(image, Path(temporary) / 'runtime', runner=update.run)
                if not all((source / name).is_file() for name in install.RUNTIME_FILES):
                    raise ValueError('Image enthält keinen vollständigen Pi-Wartungsdienst.')
            container = update.compose('ps', '-q', 'dashboard', capture=True).stdout.strip()
            if not container or '\n' in container:
                raise ValueError('Ein erreichbarer bisheriger Dashboard-Container wird für die Sicherung benötigt.')
            data = json.loads(update.compose('exec', '-T', 'dashboard', 'python', '-c', update.SNAPSHOT, capture=True).stdout)
            if not isinstance(data, dict):
                raise ValueError('Datensicherung fehlgeschlagen.')
            current_runtime = update.runtime_target()
            session_active = update.target_active()
            stamp = time.strftime('%Y%m%d-%H%M%S') + '-' + secrets.token_hex(3)
            backup = root / 'backups' / ('neuinstallation-' + stamp)
            backup.mkdir(mode=0o700, parents=True)
            backup.chmod(0o700)
            original = (root / '.env').read_text()
            install.atomic_write(backup / 'environment', original)
            install.atomic_write(backup / 'data.json', json.dumps(data))
            install.atomic_write(backup / 'installation.json', manifest_path.read_text())
            actual_image = update.run(['docker', 'inspect', '--format', '{{.Image}}', container], capture=True).stdout.strip()
            retained_image = 'oma-tv-reinstall:' + stamp
            update.run(['docker', 'tag', actual_image, retained_image])
            for path in [*owned, Path(manifest['agent_config'])]:
                if path.is_file():
                    destination = backup / 'files' / path.resolve().relative_to(home)
                    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                    install.atomic_write(destination, path.read_text())
            plan = {'phase': 'saved', 'previous_runtime': str(current_runtime), 'retained_image': retained_image,
                'target_image': image, 'session_active': session_active}
            install.atomic_write(backup / 'reinstall.json', json.dumps(plan, indent=2))
            print('Private Sicherung angelegt: ' + str(backup), flush=True)
            for unit in UNITS:
                loaded = update.run(['systemctl', '--user', 'show', unit, '--property=LoadState', '--value'], capture=True, allowed=True)
                if loaded.stdout.strip() == 'loaded':
                    update.run(['systemctl', '--user', 'stop', unit])
            # Retain interrupted transactions, but never replay them into the new installation.
            for name, destination in [('backups/update-state.json', 'previous-update-state.json'),
                    ('.maintenance/job.json', 'previous-job.json')]:
                path = root / name
                if path.exists():
                    shutil.move(str(path), str(backup / destination))
            install.atomic_write(root / '.env', update.env_for_image(original, image, tag))
            plan['phase'] = 'installing'
            install.atomic_write(backup / 'reinstall.json', json.dumps(plan, indent=2))
            # This process already holds the shared installation/update lock.
            install._install_project(root, home, image=image)
            update.run(['systemctl', '--user', 'reset-failed', 'oma-tv-agent.service', 'oma-tv-kiosk.service'])
            update.run(['systemctl', '--user', 'start', 'oma-tv-session.target' if session_active else 'oma-tv-agent.service'])
            update.wait_healthy(True)
            plan['phase'] = 'complete'
            install.atomic_write(backup / 'reinstall.json', json.dumps(plan, indent=2))
            return backup
    except Exception as error:
        if backup is not None:
            raise ValueError('Neuinstallation noch nicht erfolgreich bestätigt. Datenvolume und Sicherung bleiben erhalten: '
                + str(backup) + '. ' + (str(error) if isinstance(error, ValueError) else
                    'Dienst- oder Startprüfung fehlgeschlagen. Die angezeigte Ausgabe zur Diagnose aufbewahren.')) from None
        raise
    finally:
        update.ROOT = previous_root


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', required=True, type=install.registry_image)
    args = parser.parse_args()
    try:
        reinstall(install.project_root(__file__), Path.home(), args.image)
    except (ValueError, RuntimeError, OSError, subprocess.SubprocessError) as error:
        raise SystemExit(str(error)) from None
    print('Neuinstallation bestätigt: Dashboard, Wartungsdienst und Pi-Dienst antworten. Kamera, Taster und TV am Gerät prüfen.')


if __name__ == '__main__':
    main()
