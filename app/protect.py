"""Small local Protect Integration API client. Keys never leave the backend."""
import hashlib
import http.client
import json
import re
import socket
import ssl
from urllib.parse import urlsplit, quote

class ProtectError(Exception):
    def __init__(self, message, code=502, **details):
        super().__init__(message)
        self.code, self.details = code, details

class PinnedConnection(http.client.HTTPSConnection):
    def __init__(self, host, port, fingerprint):
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        super().__init__(host, port, timeout=8, context=context)
        self.fingerprint = fingerprint

    def connect(self):
        super().connect()
        actual = hashlib.sha256(self.sock.getpeercert(binary_form=True)).hexdigest()
        if actual != self.fingerprint:
            self.close()
            raise ProtectError('Das Protect-Zertifikat hat sich geändert. Verbindung erneut einrichten.', 409)

def normalize_host(value):
    value = str(value).strip()
    parts = urlsplit(value if '://' in value else 'https://' + value)
    try:
        port = parts.port or 443
    except ValueError:
        raise ProtectError('Ungültiger Port.', 400)
    if (parts.scheme != 'https' or not parts.hostname or parts.username or parts.password
            or parts.path not in ('', '/') or parts.query or parts.fragment
            or not re.fullmatch(r'[A-Za-z0-9.:-]+', parts.hostname)):
        raise ProtectError('Bitte nur die lokale Protect-Adresse eingeben, z. B. 192.168.1.20.', 400)
    hostname = parts.hostname.lower()
    if ':' in hostname: hostname = '[' + hostname + ']'
    return 'https://' + hostname + (':' + str(port) if port != 443 else '')

def certificate_fingerprint(host):
    parts = urlsplit(host)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    with socket.create_connection((parts.hostname, parts.port or 443), timeout=8) as sock:
        with context.wrap_socket(sock, server_hostname=parts.hostname) as tls:
            return hashlib.sha256(tls.getpeercert(binary_form=True)).hexdigest()

class Protect:
    def __init__(self, credentials):
        self.host = normalize_host(credentials.get('host', ''))
        self.key = credentials.get('api_key', '')
        self.pin = credentials.get('fingerprint', '')
        if not isinstance(self.key, str) or not self.key or len(self.key)>4096 or any(ord(c)<33 or ord(c)>126 for c in self.key):
            raise ProtectError('Bitte einen gültigen Protect-API-Schlüssel eintragen.', 400)
        if self.pin and not re.fullmatch('[a-f0-9]{64}', self.pin):
            raise ProtectError('Ungültiger Zertifikat-Fingerabdruck.', 400)

    def request(self, path, body=None, binary=False):
        p = urlsplit(self.host)
        conn = PinnedConnection(p.hostname, p.port or 443, self.pin) if self.pin else http.client.HTTPSConnection(p.hostname,p.port or 443,timeout=8,context=ssl.create_default_context())
        try:
            # Connect and authenticate the TLS peer before sending the API key.
            conn.connect()
            conn.request('POST' if body is not None else 'GET', '/proxy/protect/integration/v1/'+path,
                         body=json.dumps(body) if body is not None else None,
                         headers={'X-API-Key':self.key,'Accept':'image/jpeg' if binary else 'application/json','Content-Type':'application/json'})
            response=conn.getresponse()
            if response.status in (401,403): raise ProtectError('Protect lehnt den API-Schlüssel ab. Schlüssel und Berechtigungen prüfen.', 401)
            if response.status==404: raise ProtectError('Protect-Schnittstelle oder Kamera nicht gefunden. Protect-Adresse und Version prüfen.',404)
            if response.status==429: raise ProtectError('Protect ist ausgelastet. Bitte kurz warten und erneut versuchen.',429)
            if response.status>=300: raise ProtectError('Protect konnte die Anfrage nicht ausführen. Verbindung und Stream-Freigabe prüfen.')
            data=response.read(8*1024*1024+1)
            if len(data)>8*1024*1024: raise ProtectError('Protect-Antwort ist zu groß.')
            if binary:
                if not data.startswith(b'\xff\xd8'): raise ProtectError('Protect hat kein gültiges Kamerabild geliefert.')
                return data
            return json.loads(data)
        except ssl.SSLCertVerificationError:
            try: fingerprint=certificate_fingerprint(self.host)
            except OSError: raise ProtectError('Protect-Zertifikat konnte nicht geprüft werden.')
            raise ProtectError('Die Konsole verwendet ein eigenes Zertifikat. Vergleiche den Fingerabdruck mit deiner Konsole und bestätige ihn.',409,fingerprint=fingerprint,host=self.host)
        except (OSError, http.client.HTTPException):
            raise ProtectError('Protect ist nicht erreichbar. Adresse, Netzwerk und VPN prüfen.')
        except (ValueError, TypeError):
            raise ProtectError('Unerwartete Antwort von Protect. Version und Schnittstelle prüfen.')
        finally: conn.close()

    def camera(self, camera_id):
        return self.request('cameras/' + quote(camera_id, safe=''))

    def event_socket(self):
        import websocket
        p = urlsplit(self.host)
        # Verify the exact TLS peer BEFORE websocket-client sends the API-key header.
        conn = PinnedConnection(p.hostname, p.port or 443, self.pin) if self.pin else http.client.HTTPSConnection(p.hostname,p.port or 443,timeout=8,context=ssl.create_default_context())
        try:
            conn.connect()
            ws = websocket.create_connection('wss://' + p.netloc + '/proxy/protect/integration/v1/subscribe/events',
                socket=conn.sock, header={'X-API-Key': self.key}, timeout=8, redirect_limit=0, suppress_origin=True)
            conn.sock = None  # websocket now owns the already-verified TLS connection.
            ws.settimeout(2)
            return ws
        except ssl.SSLCertVerificationError:
            raise ProtectError('Protect-Zertifikat erneut im Kamera-Assistenten bestätigen.',409)
        except websocket.WebSocketBadStatusException as error:
            code = error.status_code
            raise ProtectError('Ereigniszugang nicht unterstützt.' if code == 404 else 'Ereigniszugang abgelehnt. Protect-Version und Schlüssel prüfen.',code if code in (401,403,404) else 502)
        except (OSError, websocket.WebSocketException):
            raise ProtectError('Ereignisverbindung zu Protect nicht erreichbar.')
        finally:
            conn.close()

    def cameras(self):
        rows=self.request('cameras')
        if not isinstance(rows,list): raise ProtectError('Unerwartete Kameraliste von Protect.')
        return [{'id':str(c['id']), 'name':str(c.get('name') or 'Kamera'), 'model':str(c.get('type') or 'UniFi Kamera'),
                 'state':str(c.get('state','UNKNOWN'))} for c in rows if isinstance(c,dict) and c.get('id')]

    def streams(self,camera_id,quality,enable=False):
        if quality not in ('high','medium','low'): raise ProtectError('Ungültige Bildqualität.',400)
        path='cameras/'+quote(camera_id,safe='')+'/rtsps-stream'
        result=self.request(path)
        if not isinstance(result,dict): raise ProtectError('Unerwartete Stream-Antwort von Protect.')
        url=result.get(quality)
        if not url and enable:
            result=self.request(path,{'qualities':[quality]})
            if not isinstance(result,dict): raise ProtectError('Unerwartete Stream-Antwort von Protect.')
            url=result.get(quality)
        if not url:
            raise ProtectError('Für diese Bildqualität ist noch kein Stream freigegeben.',409,needs_stream=True)
        if not isinstance(url,str) or not url.startswith('rtsps://'): raise ProtectError('Protect hat keinen sicheren Videostream geliefert.')
        return url

    def snapshot(self,camera_id):
        return self.request('cameras/'+quote(camera_id,safe='')+'/snapshot',binary=True)
