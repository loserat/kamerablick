"""Local UniFi OS login; credentials and session cookies stay in the backend."""
from collections import OrderedDict
from http.cookies import SimpleCookie, CookieError
import hashlib
import http.client
import json
import re
import ssl
import threading
import time
from urllib.parse import urlsplit, quote

from protect import ProtectError, PinnedConnection, IntegrationProtect, normalize_host, certificate_fingerprint

_sessions = OrderedDict()
_sessions_lock = threading.Lock()


class LocalProtect:
    def __init__(self, credentials):
        self.host = normalize_host(credentials.get('host', ''))
        self.pin = credentials.get('fingerprint', '')
        self.username, self.password = credentials.get('username', ''), credentials.get('password', '')
        if (not isinstance(self.username, str) or not self.username.strip() or len(self.username) > 256
                or any(ord(c) < 32 for c in self.username)):
            raise ProtectError('Bitte einen lokalen UniFi-Benutzernamen eingeben.', 400)
        if not isinstance(self.password, str) or not self.password or len(self.password) > 4096:
            raise ProtectError('Bitte das Passwort des lokalen UniFi-Benutzers eingeben.', 400)
        if self.pin and not re.fullmatch('[a-f0-9]{64}', self.pin):
            raise ProtectError('Ungültiger Zertifikat-Fingerabdruck.', 400)
        self.integration = IntegrationProtect(credentials) if credentials.get('api_key') else None
        identity = hashlib.sha256(json.dumps([self.host, self.pin, self.username, self.password], ensure_ascii=True).encode()).hexdigest()
        with _sessions_lock:
            if identity not in _sessions:
                _sessions[identity] = {'lock': threading.RLock(), 'headers': {}, 'expires': 0, 'blocked': 0}
            _sessions.move_to_end(identity)
            self.session = _sessions[identity]
            while len(_sessions) > 16:
                _sessions.popitem(last=False)

    def _wire(self, path, *, method='GET', body=None, headers=None, binary=False):
        parts = urlsplit(self.host)
        connection = (PinnedConnection(parts.hostname, parts.port or 443, self.pin) if self.pin
            else http.client.HTTPSConnection(parts.hostname, parts.port or 443, timeout=8, context=ssl.create_default_context()))
        try:
            connection.connect()  # Verify the peer before sending a password or session cookie.
            connection.request(method, path, body=json.dumps(body) if body is not None else None,
                headers={'Accept': 'image/jpeg' if binary else 'application/json', 'Content-Type': 'application/json', **(headers or {})})
            response = connection.getresponse()
            raw = response.read(8 * 1024 * 1024 + 1)
            if len(raw) > 8 * 1024 * 1024:
                raise ProtectError('Die Antwort der UniFi-Konsole ist zu groß.')
            if response.status in (401, 403):
                raise ProtectError('UniFi lehnt die Anmeldung ab. Lokalen Benutzer, Passwort und Protect-Berechtigung prüfen. Cloud-Login und MFA werden hier nicht unterstützt.', 401)
            if response.status == 429:
                raise ProtectError('UniFi begrenzt die Anmeldung. Bitte eine Minute warten.', 429)
            if response.status == 404:
                raise ProtectError('Der lokale Protect-Zugang ist auf dieser Konsole nicht verfügbar. Adresse und Protect-Version prüfen oder einen API-Schlüssel verwenden.', 404)
            if response.status >= 300:
                raise ProtectError('Die UniFi-Konsole konnte die Anfrage nicht ausführen. Weiterleitungen werden nicht verfolgt.')
            updated = {}
            cookies = SimpleCookie()
            for name, value in response.getheaders():
                if name.lower() == 'set-cookie':
                    # Partitioned is a browser-only attribute; Python 3.13's parser predates it.
                    cookies.load(re.sub(r';\s*Partitioned(?=;|$)', '', value, flags=re.I))
            for name in ('TOKEN', 'UOS_TOKEN'):
                if name in cookies:
                    value = cookies[name].coded_value
                    if len(value) > 8192 or any(ord(c) < 32 or ord(c) > 126 for c in value):
                        raise ProtectError('Ungültige UniFi-Sitzung.')
                    updated['Cookie'] = name + '=' + value
                    break
            csrf = response.getheader('X-CSRF-Token')
            if csrf:
                if len(csrf) > 4096 or any(ord(c) < 33 or ord(c) > 126 for c in csrf):
                    raise ProtectError('Ungültige UniFi-Sitzung.')
                updated['X-CSRF-Token'] = csrf
            if binary:
                if not raw.startswith(b'\xff\xd8'):
                    raise ProtectError('Protect hat kein gültiges Kamerabild geliefert.')
                return raw, updated
            return json.loads(raw), updated
        except ssl.SSLCertVerificationError:
            try:
                fingerprint = certificate_fingerprint(self.host)
            except OSError:
                raise ProtectError('Das UniFi-Zertifikat konnte nicht gelesen werden.')
            raise ProtectError('Die Konsole nutzt ein eigenes Zertifikat. Fingerabdruck mit deiner Konsole vergleichen und bestätigen.', 409, fingerprint=fingerprint, host=self.host)
        except (OSError, http.client.HTTPException):
            raise ProtectError('Die UniFi-Konsole ist nicht erreichbar. Adresse und Heimnetz prüfen.')
        except (ValueError, TypeError, CookieError):
            raise ProtectError('Unerwartete Antwort der UniFi-Konsole. Protect-Version und Anmeldeart prüfen.')
        finally:
            connection.close()

    def _headers(self):
        with self.session['lock']:
            now = time.monotonic()
            if self.session['headers'] and self.session['expires'] > now:
                return dict(self.session['headers'])
            if self.session['blocked'] > now:
                raise ProtectError('UniFi-Anmeldung zuletzt fehlgeschlagen. Zugang prüfen und nach einer Minute erneut versuchen.', 429)
            try:
                _, headers = self._wire('/api/auth/login', method='POST', body={
                    'username': self.username, 'password': self.password, 'rememberMe': False})
                if not headers.get('Cookie'):
                    raise ProtectError('UniFi hat keine lokale Sitzung freigegeben. Lokalen Benutzer ohne Cloud-Anmeldung verwenden.', 401)
            except ProtectError as error:
                if error.code in (401, 429):
                    self.session['blocked'] = now + 60
                raise
            self.session.update(headers=headers, expires=time.monotonic() + 300, blocked=0)
            return dict(headers)

    def _request(self, path, *, binary=False):
        for attempt in range(2):
            headers = self._headers()
            try:
                value, updated = self._wire('/proxy/protect/api/' + path, headers=headers, binary=binary)
                with self.session['lock']:
                    if self.session['headers'] == headers:
                        self.session['headers'].update(updated)
                return value
            except ProtectError as error:
                if error.code != 401:
                    raise
                with self.session['lock']:
                    if self.session['headers'] == headers:
                        self.session.update(headers={}, expires=0)
                if attempt:
                    with self.session['lock']:
                        self.session['blocked'] = time.monotonic() + 60
                    raise

    def cameras(self):
        self._headers()
        if self.integration:
            return self.integration.cameras()
        result = self._request('bootstrap')
        rows = result.get('cameras') if isinstance(result, dict) else None
        if not isinstance(rows, list):
            raise ProtectError('Die Konsole hat keine gültige Kameraliste geliefert.')
        return [{'id': str(c['id']), 'name': str(c.get('name') or 'Kamera'),
            'model': str(c.get('type') or 'UniFi Kamera'), 'state': str(c.get('state', 'UNKNOWN'))}
            for c in rows if isinstance(c, dict) and c.get('id') and c.get('isAdopted') is not False]

    def camera(self, camera_id):
        if self.integration:
            return self.integration.camera(camera_id)
        return self._request('cameras/' + quote(camera_id, safe=''))

    def snapshot(self, camera_id):
        if self.integration:
            return self.integration.snapshot(camera_id)
        return self._request('cameras/' + quote(camera_id, safe='') + '/snapshot?force=true', binary=True)

    def streams(self, camera_id, quality, enable=False):
        if quality not in ('high', 'medium', 'low'):
            raise ProtectError('Ungültige Bildqualität.', 400)
        if self.integration:
            return self.integration.streams(camera_id, quality, enable)
        camera = self.camera(camera_id)
        channels = camera.get('channels', []) if isinstance(camera, dict) else []
        channel_id = {'high': 0, 'medium': 1, 'low': 2}[quality]
        channel = next((c for c in channels if isinstance(c, dict) and c.get('id') == channel_id), {}) if isinstance(channels, list) else {}
        alias = channel.get('rtspAlias')
        if channel.get('isRtspEnabled') is not True or not isinstance(alias, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,1024}', alias):
            raise ProtectError('Für diesen Stream einen API-Schlüssel unter „Zugang ändern“ ergänzen oder die gewählte RTSP-Qualität direkt in Protect freigeben. Die Aufnahme wird hier nicht verändert.', 409, needs_api_key=True)
        host = urlsplit(self.host).hostname
        if ':' in host:
            host = '[' + host + ']'
        return 'rtsps://' + host + ':7441/' + quote(alias, safe='') + '?enableSrtp'

    def event_socket(self):
        if self.integration:
            return self.integration.event_socket()
        raise ProtectError('Für laufende Bewegungsereignisse unter „Zugang ändern“ zusätzlich einen Protect-API-Schlüssel hinterlegen.', 404)
