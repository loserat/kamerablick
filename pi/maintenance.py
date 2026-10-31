"""Loopback-only maintenance bridge. The dashboard never gets a Docker socket."""
import argparse
import fcntl
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import subprocess
import threading
import time

from install import atomic_write, project_root, read_env
import release_info

TERMINAL = {'complete', 'rolled_back', 'failed', 'recovery_failed'}
MESSAGES = {
    'queued': 'Aktualisierung wird vorbereitet.',
    'checking': 'Veröffentlichte Version wird geprüft.',
    'downloading': 'Neue Version wird heruntergeladen.',
    'backing_up': 'Einstellungen und Zugangsdaten werden gesichert.',
    'installing': 'Anwendung und Pi-Dienste werden aktualisiert.',
    'verifying': 'Die neue Version und ihre Dienste werden geprüft.',
    'rolling_back': 'Vorherige Version und Einstellungen werden wiederhergestellt.',
    'recovering': 'Unterbrochene Aktualisierung wird wiederhergestellt.',
    'complete': 'Aktualisierung abgeschlossen. Kamera, Taster und TV zusätzlich prüfen.',
    'rolled_back': 'Aktualisierung fehlgeschlagen. Vorherige Version und Einstellungen sind wieder aktiv.',
    'failed': 'Aktualisierung nicht übernommen. Der bisherige Stand bleibt erhalten.',
    'recovery_failed': 'Wiederherstellung benötigt Hilfe über den privaten Wartungszugang.',
}


class Store:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.directory = self.root / '.maintenance'
        if self.directory.is_symlink():
            raise ValueError('Privates Wartungsverzeichnis erforderlich.')
        self.directory.mkdir(mode=0o700, exist_ok=True)
        self.directory.chmod(0o700)
        self.path = self.directory / 'job.json'
        self.lock = threading.RLock()

    def read(self):
        with self.lock:
            return json.loads(self.path.read_text()) if self.path.exists() else None

    def write(self, job):
        with self.lock:
            atomic_write(self.path, json.dumps(job) + '\n')

    def phase(self, phase, **extra):
        if phase not in MESSAGES:
            raise ValueError('Unbekannter Wartungsschritt')
        with self.lock:
            job = self.read()
            if not job:
                raise ValueError('Wartungsauftrag fehlt')
            job.update(phase=phase, updated_at=time.time(), **extra)
            self.write(job)

    def public(self):
        job = self.read()
        if not job:
            return None
        result = {key: job.get(key) for key in ('id', 'version', 'previous_version', 'phase', 'created_at', 'updated_at')}
        result['message'] = MESSAGES.get(job.get('phase'), 'Wartungsstatus unbekannt.')
        result['busy'] = job.get('phase') not in TERMINAL
        return result


def persistent_user():
    try:
        result = subprocess.run(['loginctl', 'show-user', str(os.getuid()), '--property=Linger', '--value'],
            capture_output=True, text=True, timeout=3)
        return result.returncode == 0 and result.stdout.strip() == 'yes'
    except (OSError, subprocess.TimeoutExpired):
        return False


def unit_active(unit):
    try:
        result = subprocess.run(['systemctl', '--user', 'show', unit, '--property=ActiveState', '--value'],
            capture_output=True, text=True, timeout=3)
        return result.returncode == 0 and result.stdout.strip() in ('active', 'activating', 'reloading')
    except (OSError, subprocess.TimeoutExpired):
        return False


class Maintenance:
    def __init__(self, root, *, scheduler=None, persistent=persistent_user, active=unit_active):
        self.root = Path(root).resolve()
        self.store = Store(self.root)
        self.persistent, self.active = persistent, active
        self.scheduler = scheduler or self.schedule
        self.lock = threading.RLock()
        self.identity = hashlib.sha256(str(self.root).encode()).hexdigest()
        self.runtime = Path(__file__).resolve().parent.name

    def managed(self):
        try:
            manifest = json.loads((self.root / '.install.json').read_text())
            return Path(manifest['root']).resolve() == self.root and (self.root / '.runtime/current').is_symlink()
        except (OSError, ValueError, KeyError):
            return False

    def status(self):
        ready = self.managed()
        if ready:
            self.reconcile()
        persistent = self.persistent()
        return {'protocol': 1, 'available': ready, 'persistent': persistent, 'instance': self.identity,
            'runtime': self.runtime, 'current_version': read_env(self.root / '.env').get('APP_VERSION', 'dev'),
            'job': self.store.public(), 'message': ('Bereit für Updates aus der Oberfläche.' if ready and persistent
                else 'Einmalig dauerhaften Wartungsdienst freigeben: sudo loginctl enable-linger "$USER"' if ready
                else 'Verwaltete Pi-Installation fehlt.')}

    def schedule(self, job, recover=False):
        runtime = (self.root / '.runtime/current').resolve()
        if not runtime.is_relative_to((self.root / '.runtime/releases').resolve()):
            raise ValueError('Unbekannte Pi-Laufzeit')
        command = ['systemd-run', '--user', '--collect', '--unit=' + job['unit'],
            '--property=Type=exec', '--property=NoNewPrivileges=yes', '--property=UMask=0077',
            '--working-directory=' + str(self.root), '/usr/bin/python3', str(runtime / 'update_job.py').replace('$','$$'),
            '--root', str(self.root).replace('$','$$'), '--job', job['id']]
        if recover:
            command.append('--recover')
        subprocess.run(command, check=True, capture_output=True, text=True, timeout=10)

    def start(self, tag):
        release_info.version(tag)
        with self.lock:
            if not self.managed() or not self.persistent():
                raise ValueError('Wartungsdienst einmalig einrichten und dauerhaft freigeben. Anleitung unter Browser-Updates beachten.')
            old = self.store.read()
            if old and old.get('phase') not in TERMINAL:
                raise ValueError('Eine Aktualisierung läuft bereits. Bitte ihren Abschluss abwarten.')
            current = read_env(self.root / '.env').get('APP_VERSION', '')
            if not release_info.newer(tag, current):
                raise ValueError('Nur eine neuere stabile Version kann installiert werden.')
            release_info.release(tag, refresh=True)
            # An independently started CLI update must never overlap a browser job.
            with open(self.root / '.update.lock', 'a') as handle:
                try:
                    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    raise ValueError('Auf dem Pi läuft bereits ein Update.') from None
            watch = secrets.token_urlsafe(32)
            job_id = secrets.token_hex(12)
            job = {'id': job_id, 'version': tag, 'previous_version': current, 'phase': 'queued',
                'created_at': time.time(), 'updated_at': time.time(), 'unit': 'kamerablick-update-' + job_id,
                'watch_hash': hashlib.sha256(watch.encode()).hexdigest()}
            self.store.write(job)
            try:
                self.scheduler(job)
            except Exception:
                self.store.phase('failed')
                raise ValueError('Der Pi konnte den Updateauftrag nicht starten. Wartungsdienst prüfen.') from None
            return {'job': self.store.public(), 'watch': watch}

    def watch(self, token):
        self.reconcile()
        job = self.store.read()
        if (not isinstance(token, str) or not 32 <= len(token) <= 128 or not job
                or time.time() - job['created_at'] > 24 * 3600
                or not secrets.compare_digest(hashlib.sha256(token.encode()).hexdigest(), job.get('watch_hash', ''))):
            raise PermissionError('Statusfreigabe ungültig. Bitte erneut am Dashboard anmelden.')
        return {'job': self.store.public()}

    def reconcile(self):
        """Recover after loss of power, never while the detached worker holds the lock."""
        with self.lock:
            job = self.store.read()
            pending = self.root / 'backups/update-state.json'
            state = json.loads(pending.read_text()) if pending.exists() else {}
            if job and job.get('phase')=='recovery_failed' and job.get('recovery_attempts',0)>=1:
                if state.get('phase')=='rolled_back':
                    self.store.phase('rolled_back')
                return
            if job and job.get('phase') in TERMINAL and state.get('phase') not in ('applying','rollback_failed'):
                return
            if job and self.active(job['unit']):
                return
            with open(self.root / '.update.lock', 'a') as handle:
                try:
                    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    return
                if state.get('phase') not in ('applying', 'rollback_failed'):
                    if job:
                        self.store.phase('failed')
                    return
                if not job:
                    job_id = secrets.token_hex(12)
                    job = {'id': job_id, 'version': None, 'previous_version': None,
                        'created_at': time.time(), 'watch_hash': ''}
                job.update(phase='recovering', updated_at=time.time(), unit='kamerablick-recover-' + job['id'],recovery_attempts=job.get('recovery_attempts',0)+1)
                self.store.write(job)
            try:
                self.scheduler(job, recover=True)
            except Exception:
                self.store.phase('recovery_failed')


def handler(manager, token):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def reply(self, value, status=200):
            raw = json.dumps(value).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(raw)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            try:
                self.wfile.write(raw)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def authorized(self):
            return (self.client_address[0] in ('127.0.0.1', '::1') and
                secrets.compare_digest(self.headers.get('Authorization', ''), 'Bearer ' + token))

        def do_GET(self):
            if not self.authorized():
                return self.reply({'error': 'Lokaler Wartungszugang erforderlich.'}, 401)
            if self.path != '/status':
                return self.reply({'error': 'Nicht gefunden.'}, 404)
            try:
                self.reply(manager.status())
            except Exception:
                self.reply({'error': 'Wartungsstatus nicht lesbar.'}, 503)

        def do_POST(self):
            if not self.authorized():
                return self.reply({'error': 'Lokaler Wartungszugang erforderlich.'}, 401)
            try:
                size = int(self.headers.get('Content-Length', 0))
                if not 0 < size <= 2048:
                    raise ValueError('Ungültige Anfragegröße.')
                body = json.loads(self.rfile.read(size))
                if not isinstance(body, dict):
                    raise ValueError('Ungültige Anfrage.')
                if self.path == '/update':
                    return self.reply(manager.start(body.get('version')), 202)
                if self.path == '/watch':
                    return self.reply(manager.watch(body.get('watch')))
                self.reply({'error': 'Nicht gefunden.'}, 404)
            except PermissionError as error:
                self.reply({'error': str(error)}, 401)
            except (ValueError, TypeError) as error:
                self.reply({'error': str(error)}, 409)
            except Exception:
                self.reply({'error': 'Wartungsauftrag fehlgeschlagen.'}, 503)
    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=project_root(__file__))
    args = parser.parse_args()
    token = os.getenv('AGENT_TOKEN', '')
    if len(token) < 24:
        raise SystemExit('Lokaler Wartungsschlüssel fehlt.')
    manager = Maintenance(args.root)
    manager.reconcile()
    ThreadingHTTPServer(('127.0.0.1', 8093), handler(manager, token)).serve_forever()


if __name__ == '__main__':
    main()
