"""Bounded read-only mpv IPC sampling; process life alone is not playback."""
import json
import math
import socket
import time


def read_progress(path, timeout=.35):
    deadline = time.monotonic() + timeout
    properties = {1: 'time-pos', 2: 'video-out-params'}
    payload = b''.join((json.dumps({'command': ['get_property', name], 'request_id': key}) + '\n').encode()
                       for key, name in properties.items())
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.settimeout(timeout)
        connection.connect(str(path))
        connection.sendall(payload)
        buffer, responses, total = b'', {}, 0
        while len(responses) < len(properties):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError('Player-Prüfung abgelaufen')
            connection.settimeout(remaining)
            chunk = connection.recv(4096)
            if not chunk:
                raise ValueError('Player-Verbindung beendet')
            total += len(chunk)
            if total > 65536:
                raise ValueError('Player-Antwort zu groß')
            buffer += chunk
            while b'\n' in buffer:
                line, buffer = buffer.split(b'\n', 1)
                response = json.loads(line)
                if not isinstance(response, dict):
                    continue
                key = response.get('request_id')
                if type(key) is int and key in properties:
                    if response.get('error') != 'success':
                        raise ValueError('Player-Fortschritt noch nicht verfügbar')
                    responses[key] = response.get('data')
        position, video = responses[1], responses[2]
        if type(position) not in (int, float) or not math.isfinite(position):
            raise ValueError('Ungültige Wiedergabezeit')
        if not isinstance(video, dict) or not all(type(video.get(axis)) in (int, float) and video[axis] > 0 for axis in ('w', 'h')):
            raise ValueError('Keine Videoausgabe gemeldet')
        return float(position)


class PlayerHealth:
    def __init__(self, clock=time.monotonic, reader=read_progress, startup=30, stalled=20):
        self.clock, self.reader = clock, reader
        self.startup, self.stalled = startup, stalled
        self.clear()

    def clear(self):
        self.path = None
        self.started = self.last_progress = self.last_sample = self.healthy_since = None
        self.position = None
        self.sample_ok = False
        self.next_sample = 0

    def begin(self, path):
        self.clear()
        self.path = path
        self.started = self.clock()

    def sample(self):
        now = self.clock()
        if self.path is None or now < self.next_sample:
            return
        if self.last_sample is not None and now - self.last_sample > 3:
            self.healthy_since = None
        self.next_sample = now + 1
        self.last_sample = now
        try:
            position = self.reader(self.path)
            changed = self.position is not None and abs(position - self.position) > .01
            self.position, self.sample_ok = position, True
            if changed:
                self.last_progress = now
                if self.healthy_since is None:
                    self.healthy_since = now
            elif self.last_progress is None or now - self.last_progress > 5:
                self.healthy_since = None
        except (OSError, ValueError, TypeError):
            self.sample_ok = False
            self.healthy_since = None

    def snapshot(self):
        now = self.clock()
        if self.started is None:
            return {'state': 'stopped', 'progress_fresh': False, 'restart_due': False,
                    'last_progress_age_seconds': None, 'stable': False}
        age = None if self.last_progress is None else max(0, now - self.last_progress)
        fresh = bool(self.sample_ok and self.last_sample is not None and now - self.last_sample <= 3 and age is not None and age <= 5)
        overdue = now - self.started >= self.startup if age is None else age >= self.stalled
        state = 'playing' if fresh else 'stalled' if age is not None and age > 5 else 'starting' if now - self.started < self.startup else 'unavailable'
        return {'state': state, 'progress_fresh': fresh, 'restart_due': overdue,
                'last_progress_age_seconds': None if age is None else int(age),
                'stable': bool(fresh and self.healthy_since is not None and now - self.healthy_since >= 10)}
