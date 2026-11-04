"""Read-only installation diagnosis. Never outputs credentials or changes TV state."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import urllib.error
import urllib.request

from install import MANAGED, project_root, read_env

UNITS = ('oma-tv-agent.service', 'oma-tv-kiosk.service', 'oma-tv-maintenance.service')


def command(args, root):
    try:
        result = subprocess.run(args, cwd=root, capture_output=True, text=True, timeout=8)
        return result.stdout.strip() if result.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def local_json(port, path, token='', body=None):
    # No redirects: a diagnostic request must never forward the local host key.
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            return None
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    headers = {'Content-Type': 'application/json'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    request = urllib.request.Request('http://127.0.0.1:' + str(port) + path,
        data=json.dumps(body).encode() if body is not None else None, headers=headers)
    try:
        with opener.open(request, timeout=3) as response:
            raw = response.read(65537)
    except urllib.error.HTTPError as error:
        error.close()
        raise OSError('Lokale Statusabfrage abgelehnt') from None
    if len(raw) > 65536:
        raise ValueError('Antwort zu groß')
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError('Ungültige Antwort')
    return value


def diagnose(root, home):
    root, home = Path(root).resolve(), Path(home).resolve()
    checks = []
    def add(key, label, passed, good, bad, warning=False):
        checks.append({'id': key, 'label': label, 'status': 'ok' if passed else 'warn' if warning else 'fail',
            'detail': good if passed else bad})
    def probe(port, path, token='', body=None):
        try:
            return local_json(port, path, token, body)
        except (OSError, ValueError):
            return {}
    try:
        settings = read_env(root / '.env')
    except (OSError, ValueError):
        settings = {}
    add('settings', 'Installation', bool(settings), 'Lokale Einstellungen lesbar.', '.env fehlt oder ist nicht lesbar.')
    private = home / '.config/oma-tv/agent.env'
    try:
        host_settings = read_env(private)
    except (OSError, ValueError):
        host_settings = {}
    token = settings.get('AGENT_TOKEN', '')
    key_matches = len(token) >= 24 and secrets.compare_digest(token, host_settings.get('AGENT_TOKEN', ''))
    add('host_key', 'Pi-Schlüssel', key_matches, 'Dashboard und Pi-Dienste verwenden denselben Schlüssel.',
        'Pi-Schlüssel fehlt oder stimmt nicht überein. Installer erneut prüfen.')
    files_private = True
    for file in (root / '.env', private):
        try:
            stat = file.stat()
            files_private &= stat.st_uid == os.getuid() and not stat.st_mode & 0o077
        except OSError:
            files_private = False
    add('private_files', 'Dateirechte', files_private, 'Zugangswerte nur für den eigenen Benutzer lesbar.',
        '.env und agent.env müssen dem Benutzer gehören und privat lesbar sein.')
    runtime = root / '.runtime/current'
    try:
        release = runtime.resolve(strict=True)
        managed = runtime.is_symlink() and release.is_relative_to(root / '.runtime/releases')
        manifest = json.loads((root / '.install.json').read_text())
        managed &= Path(manifest['root']).resolve() == root
    except (OSError, ValueError, KeyError, TypeError):
        managed, release = False, None
    add('runtime', 'Pi-Laufzeit', managed, 'Verwaltete Laufzeit vorhanden.', 'Installationsdaten oder Pi-Laufzeit fehlen.')
    units = home / '.config/systemd/user'
    for name in UNITS:
        try:
            text = (units / name).read_text()
            paths = [line for line in text.splitlines() if line.startswith('EnvironmentFile=')]
            valid = text.startswith(MANAGED) and paths == ['EnvironmentFile=' + str(private)]
        except OSError:
            valid = False
        add(name + ':env', name + ' · Einstellungen', valid, 'Korrekter Ladepfad.',
            'Dienstdatei fehlt oder lädt agent.env falsch. Installer erneut ausführen.')
        state = command(['systemctl', '--user', 'show', name, '--property=ActiveState', '--value'], root)
        add(name, name, state == 'active', 'Läuft.',
            'Nicht aktiv oder nicht prüfbar. Grafische Sitzung und Dienst prüfen.')
    linger = command(['loginctl', 'show-user', str(os.getuid()), '--property=Linger', '--value'], root)
    add('linger', 'Dauerhafte Wartung', linger == 'yes', 'Benutzer-Dienste laufen ohne SSH-Anmeldung weiter.',
        'Einmalig ausführen: sudo loginctl enable-linger "$USER"')
    try:
        text = (home / '.config/autostart/kamerablick.desktop').read_text()
        autostart = text.startswith(MANAGED) and str(runtime / 'session.py') in text
    except OSError:
        autostart = False
    add('autostart', 'Desktop-Autostart', autostart, 'Startbrücke eingerichtet. Neustart am TV separat prüfen.',
        'Startbrücke fehlt. Installer und Desktop-Autologin prüfen.')
    port = settings.get('PORT', '8088')
    valid_port = bool(re.fullmatch(r'[0-9]{1,5}', port)) and 1024 <= int(port) <= 65535
    health = probe(int(port), '/healthz') if valid_port else {}
    add('dashboard', 'Dashboard', health.get('ok') is True, 'Lokaler Bereitschaftstest erfolgreich.',
        'Dashboard nicht bereit. Docker-Container und Port prüfen.')
    binding = settings.get('BIND')
    add('lan', 'Browser im Heimnetz', binding == '0.0.0.0', 'Für Heimnetzzugriff konfiguriert. Vom zweiten Gerät prüfen.',
        'Nur lokal oder ungültig gebunden. Hinweise unter docs/INSTALLATION.md beachten.', warning=True)
    raw = command(['docker', 'compose', 'ps', '--all', '--format', 'json', 'dashboard'], root)
    try:
        rows = json.loads(raw) if raw is not None else []
        row = rows[0] if isinstance(rows, list) and rows else rows
        running = row.get('State') == 'running' and row.get('Health') == 'healthy'
        image_matches = bool(settings.get('OMA_TV_IMAGE')) and row.get('Image') == settings['OMA_TV_IMAGE']
    except (ValueError, AttributeError, TypeError):
        running, image_matches = False, False
    add('container', 'Docker-Container', running, 'Läuft und ist gesund.', 'Container fehlt, ist gestoppt oder nicht gesund.')
    add('image', 'Installiertes Image', image_matches, 'Laufendes Image entspricht .env.',
        'Laufendes Image und .env stimmen nicht überein oder sind nicht prüfbar.')
    maintenance = probe(8093, '/healthz', token) if key_matches else {}
    identity = hashlib.sha256(str(root).encode()).hexdigest()
    ready = (maintenance.get('protocol') == 1 and maintenance.get('available') is True
        and maintenance.get('persistent') is True and maintenance.get('instance') == identity
        and release is not None and maintenance.get('runtime') == release.name
        and maintenance.get('current_version') == settings.get('APP_VERSION'))
    add('maintenance', 'Browser-Updates', ready, 'Authentifizierter Wartungsdienst für diese Installation bereit.',
        'Wartung nicht bereit oder ältere Version ohne Diagnose-Endpunkt. docs/BROWSER-UPDATES.md prüfen.')
    agent = probe(8091, '/action', token, {'action': 'status'}) if key_matches else {}
    add('agent', 'Pi-Dienst antwortet', isinstance(agent.get('active'), bool) and isinstance(agent.get('gpio_pin'), int),
        'Authentifizierte Statusabfrage erfolgreich. Kein TV-Befehl gesendet.', 'Pi-Dienst antwortet nicht mit gültigem Status.')
    version = settings.get('APP_VERSION', '')
    return {'schema': 1, 'version': version if re.fullmatch(r'v[0-9]+\.[0-9]+\.[0-9]+', version) else 'unbekannt',
        'read_only': True, 'hardware_verified': False, 'checks': checks}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=project_root(__file__))
    parser.add_argument('--json', action='store_true', help='Bericht ohne Zugangswerte ausgeben')
    args = parser.parse_args()
    report = diagnose(args.root, Path.home())
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        for check in report['checks']:
            print({'ok': 'OK   ', 'warn': 'HINWEIS', 'fail': 'FEHLT'}[check['status']], check['label'] + ':', check['detail'])
        print('Dies prüft die Installation. Livebild, Taster, CEC, WLAN-Neustart und VPN am Gerät separat prüfen.')
    raise SystemExit(1 if any(c['status'] == 'fail' for c in report['checks']) else 0)


if __name__ == '__main__':
    main()
