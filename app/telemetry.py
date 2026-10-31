"""Local Protect camera health and received-only event history; never invent state."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile
import threading
import time

from protect import Protect, ProtectError, normalize_host

POLL_INTERVAL = 15
STALE_AFTER = 45
SMART_EVENTS = {'smartDetectZone', 'smartDetectLine', 'smartDetectLoiterZone'}
EVENT_FIELDS = ('last_motion', 'last_person', 'last_vehicle')


def iso(seconds):
    return datetime.fromtimestamp(seconds, timezone.utc).isoformat(timespec='seconds')


def context(config, credentials):
    source = config.get('camera_source')
    if source != 'protect' or not config.get('camera_id') or not credentials:
        return {'enabled': False, 'reason': 'demo' if source == 'demo' else 'manual' if config.get('stream_url') else 'unconfigured', 'signature': ''}
    host = normalize_host(credentials.get('host', ''))
    camera = str(config['camera_id'])
    identity = hashlib.sha256((host + '\0' + camera).encode()).hexdigest()
    signature = hashlib.sha256(json.dumps([identity, credentials], sort_keys=True).encode()).hexdigest()
    return {'enabled': True, 'identity': identity, 'signature': signature, 'camera_id': camera, 'credentials': dict(credentials)}


def inactive(reason='unconfigured'):
    return {'enabled': False, 'reason': reason, 'camera_state': 'UNKNOWN', 'camera_fresh': False,
        'checked_at': None, 'model': None, 'events_state': 'disabled', 'events_fresh': False,
        'events_checked_at': None, 'motion_active': None, 'history_scope': 'received_only',
        'coverage_since': None, 'last_error': None, 'supported_smart': None,
        **{key: None for key in EVENT_FIELDS}}


class Telemetry:
    def __init__(self, path, get_config, get_credentials, *, wall=time.time, mono=time.monotonic, client_factory=Protect, ping_interval=15, pong_timeout=10):
        self.path = Path(path)
        self.get_config, self.get_credentials = get_config, get_credentials
        self.wall, self.mono, self.factory = wall, mono, client_factory
        self.ping_interval, self.pong_timeout = ping_interval, pong_timeout
        self.lock = threading.RLock()
        self.stop = threading.Event()
        self.threads = []
        self.signature = ''
        self.identity = None
        self.state = inactive()
        self.poll_mono = None
        self.events_mono = None
        self.active_motion = {}
        self.motion_mono = None
        self.motion_uncertain = False
        self.ended_motion = {}
        self.poll_error = None
        self.events_error = None
        self.socket = None
        self.store = {'schema': 1, 'cameras': {}}
        self.storage_error = False
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text())
                if data.get('schema') != 1 or not isinstance(data.get('cameras'), dict):
                    raise ValueError('Unbekanntes Format')
                self.store = data
            except (OSError, ValueError, AttributeError):
                # Preserve the original file for recovery; never silently replace corruption.
                self.storage_error = True

    def spec(self):
        try:
            return context(self.get_config(), self.get_credentials())
        except (ProtectError, ValueError, TypeError, AttributeError, OSError):
            return {'enabled': False, 'reason': 'configuration_error', 'signature': ''}

    def select(self, spec):
        with self.lock:
            latest = self.spec()
            if latest != spec:
                spec = latest
            signature = spec['signature'] if spec['enabled'] else 'disabled:' + spec['reason']
            if signature == self.signature:
                return
            self.signature = signature
            self.identity = spec.get('identity')
            self.state = inactive(spec.get('reason'))
            self.state['enabled'] = spec['enabled']
            self.poll_mono = self.events_mono = None
            self.active_motion = {}
            self.motion_mono = None
            self.motion_uncertain = False
            self.ended_motion = {}
            self.poll_error = self.events_error = None
            if spec['enabled']:
                self.state['events_state'] = 'connecting'
                history = self.store['cameras'].get(self.identity, {})
                if not isinstance(history, dict):
                    history = {}
                for key in EVENT_FIELDS:
                    event = history.get(key)
                    if isinstance(event, dict) and isinstance(event.get('occurred_at'), str) and isinstance(event.get('received_at'), str):
                        try:
                            datetime.fromisoformat(event['occurred_at'])
                            datetime.fromisoformat(event['received_at'])
                            # Whitelist fields when restoring from disk; no raw event payload.
                            self.state[key] = {k: event[k] for k in ('occurred_at', 'received_at')}
                        except (ValueError, KeyError):
                            pass

    def current(self, spec):
        return spec['enabled'] and self.spec().get('signature') == spec['signature'] and self.signature == spec['signature']

    def snapshot(self):
        spec = self.spec()
        self.select(spec)
        with self.lock:
            result = dict(self.state)
            result['camera_fresh'] = self.poll_mono is not None and self.mono() - self.poll_mono <= STALE_AFTER and not self.poll_error
            result['events_fresh'] = (self.events_mono is not None and self.mono() - self.events_mono <= STALE_AFTER
                and result['events_state'] == 'connected')
            if not result['events_fresh'] or not result['camera_fresh'] or result['camera_state'] != 'CONNECTED' or self.motion_mono is None or self.mono()-self.motion_mono>120:
                result['motion_active'] = None
            result['last_error'] = ('Gespeicherte Ereignisdatei ist nicht lesbar. Sicherung prüfen.' if self.storage_error
                else self.poll_error or self.events_error)
            return result

    def poll(self, spec):
        try:
            camera = self.factory(spec['credentials']).camera(spec['camera_id'])
            if not isinstance(camera, dict) or camera.get('id') != spec['camera_id']:
                raise ProtectError('Kameradaten konnten nicht zugeordnet werden.')
            if not self.current(spec):
                return
            with self.lock:
                self.state.update(camera_state=camera.get('state') if camera.get('state') in ('CONNECTED','CONNECTING','DISCONNECTED') else 'UNKNOWN',
                    model=str(camera.get('type') or 'UniFi Kamera'), checked_at=iso(self.wall()))
                flags = camera.get('featureFlags', {})
                supported = flags.get('smartDetectTypes') if isinstance(flags, dict) else None
                self.state['supported_smart'] = [v for v in ('person','vehicle') if v in supported] if isinstance(supported, list) else None
                self.poll_mono = self.mono()
                self.poll_error = None
        except Exception as error:
            if self.current(spec):
                with self.lock:
                    self.poll_error = str(error) if isinstance(error, ProtectError) else 'Kamerastatus konnte nicht aktualisiert werden.'

    def connected(self, spec):
        if not self.current(spec):
            return
        with self.lock:
            self.active_motion = {}
            self.motion_mono = None
            self.motion_uncertain = False
            self.ended_motion = {}
            self.state.update(events_state='connected', motion_active=None, coverage_since=iso(self.wall()))
            self.events_error = None
            self.touch(spec)

    def touch(self, spec):
        if self.current(spec):
            with self.lock:
                self.events_mono = self.mono()
                self.state['events_checked_at'] = iso(self.wall())

    def disconnected(self, spec, error):
        if not self.current(spec):
            return
        with self.lock:
            code = getattr(error, 'code', None)
            self.state['events_state'] = ('unsupported' if code == 404 else 'auth_error' if code in (401,403)
                else 'certificate_error' if code == 409 else 'reconnecting')
            self.state['motion_active'] = None
            self.active_motion = {}
            self.events_error = str(error) if isinstance(error, ProtectError) else 'Ereignisverbindung unterbrochen. Neuer Versuch folgt.'

    def persist(self):
        if self.storage_error:
            return
        entry = {key: self.state[key] for key in EVENT_FIELDS if self.state[key] is not None}
        self.store['cameras'][self.identity] = entry
        # Bound history to 32 configured cameras, keeping only the last timestamps.
        if len(self.store['cameras']) > 32:
            others = [key for key in self.store['cameras'] if key != self.identity]
            self.store['cameras'].pop(others[0], None)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix='.telemetry-', dir=self.path.parent)
        try:
            with os.fdopen(fd, 'w') as f:
                json.dump(self.store, f)
                f.flush()
                os.fsync(f.fileno())
            os.chmod(temporary, 0o600)
            os.replace(temporary, self.path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def event(self, spec, message):
        if not self.current(spec) or not isinstance(message, dict) or message.get('type') not in ('add','update'):
            return
        item = message.get('item')
        if not isinstance(item, dict) or item.get('modelKey') != 'event' or item.get('device') != spec['camera_id']:
            return
        kind = item.get('type')
        if kind != 'motion' and kind not in SMART_EVENTS:
            return
        start = item.get('start')
        if isinstance(start, bool) or not isinstance(start, (int,float)) or not 946684800000 <= start <= (self.wall()+300)*1000:
            return
        end = item.get('end')
        if end is not None and (isinstance(end,bool) or not isinstance(end,(int,float)) or end < start or end > (self.wall()+300)*1000):
            return
        event_id = item.get('id')
        if not isinstance(event_id, str) or not event_id or len(event_id)>200:
            return
        record = {'occurred_at': iso(start/1000), 'received_at': iso(self.wall())}
        fields = ['last_motion'] if kind == 'motion' else []
        smart = item.get('smartDetectTypes', [])
        if kind in SMART_EVENTS and isinstance(smart, list):
            fields.extend('last_' + value for value in ('person','vehicle') if value in smart)
        with self.lock:
            if not self.current(spec):
                return
            if kind == 'motion':
                self.motion_mono = self.mono()
                if len(self.active_motion)>=128 and event_id not in self.active_motion:
                    self.active_motion.pop(next(iter(self.active_motion)))
                    self.motion_uncertain = True
                if end is None:
                    if event_id not in self.ended_motion and start/1000>=self.wall()-120:
                        self.active_motion[event_id] = self.mono()
                else:
                    self.active_motion.pop(event_id, None)
                    self.ended_motion[event_id] = self.mono()
                    if len(self.ended_motion)>256:
                        self.ended_motion.pop(next(iter(self.ended_motion)))
                self.state['motion_active'] = True if self.active_motion else None if self.motion_uncertain else False
            changed = False
            for field in fields:
                old = self.state[field]
                if old is None or record['occurred_at'] > old['occurred_at']:
                    self.state[field] = record
                    changed = True
            if changed:
                try:
                    self.persist()
                except OSError:
                    self.storage_error = True

    def _poll_loop(self):
        while not self.stop.is_set():
            spec = self.spec()
            self.select(spec)
            if spec['enabled']:
                self.poll(spec)
            # Recheck camera/credentials at least once per second without polling NVR every second.
            for _ in range(POLL_INTERVAL):
                if self.stop.wait(1) or self.spec().get('signature') != spec.get('signature'):
                    break

    def _events_loop(self):
        import websocket
        delay = 1
        while not self.stop.is_set():
            spec = self.spec()
            self.select(spec)
            if not spec['enabled']:
                self.stop.wait(1)
                continue
            ws = None
            try:
                ws = self.factory(spec['credentials']).event_socket()
                self.socket = ws
                self.connected(spec)
                next_ping = self.mono()+self.ping_interval
                pending_ping = None
                while not self.stop.is_set() and self.current(spec):
                    now = self.mono()
                    if pending_ping is not None and now-pending_ping > self.pong_timeout:
                        raise TimeoutError('Keine Antwort auf den Verbindungscheck')
                    if now >= next_ping and pending_ping is None:
                        ws.ping(b'kamerablick')
                        pending_ping = now
                        next_ping = now+self.ping_interval
                    try:
                        opcode, data = ws.recv_data(control_frame=True)
                    except websocket.WebSocketTimeoutException:
                        continue
                    if opcode == websocket.ABNF.OPCODE_CLOSE:
                        raise ConnectionError('Verbindung beendet')
                    self.touch(spec)
                    if opcode == websocket.ABNF.OPCODE_PONG and data == b'kamerablick':
                        pending_ping = None
                        delay = 1
                    if opcode == websocket.ABNF.OPCODE_TEXT:
                        if len(data)>1024*1024:
                            raise ValueError('Ereignis zu groß')
                        try:
                            self.event(spec, json.loads(data))
                        except (ValueError, TypeError):
                            pass
            except Exception as error:
                self.disconnected(spec, error)
            finally:
                self.socket = None
                if ws:
                    try: ws.close(timeout=0.2)
                    except Exception: pass
                    finally:
                        ws.shutdown()
            # Retry errors, graceful closes and revoked keys; configuration changes interrupt backoff.
            for _ in range(delay):
                if self.stop.wait(1) or self.spec().get('signature') != spec.get('signature'):
                    break
            delay = min(60, delay*2)

    def start(self):
        import websocket  # Fail explicitly when the required dependency is missing.
        for target in (self._poll_loop, self._events_loop):
            thread = threading.Thread(target=target, daemon=True)
            self.threads.append(thread)
            thread.start()

    def close(self):
        self.stop.set()
        if self.socket:
            try: self.socket.abort()
            except Exception: pass
        for thread in self.threads:
            thread.join(timeout=10)
