"""One libCEC owner for TV commands and a bounded, short-lived input channel."""
from collections import deque
from datetime import datetime, timezone
import re
import subprocess
import selectors
import os
import secrets
import threading
import time
from array import array
from pathlib import Path
import fcntl

KEYS = {0x00: 'Enter', 0x01: 'ArrowUp', 0x02: 'ArrowDown',
        0x03: 'ArrowLeft', 0x04: 'ArrowRight', 0x0d: 'Escape'}
LABELS = {'Enter': 'OK', 'ArrowUp': 'Hoch', 'ArrowDown': 'Runter',
          'ArrowLeft': 'Links', 'ArrowRight': 'Rechts', 'Escape': 'Zurück'}


def connected_adapter(directory=Path('/dev')):
    """Read the kernel's EDID-derived address; never take over a CEC adapter."""
    for device in sorted(directory.glob('cec[0-9]*')):
        if not re.fullmatch(r'cec[0-9]+', device.name):
            continue
        try:
            with device.open('rb', buffering=0) as handle:
                address = array('H', [0xffff])
                # Linux CEC_ADAP_G_PHYS_ADDR, _IOR('a', 1, __u16).
                fcntl.ioctl(handle, 0x80026101, address, True)
            if address[0] != 0xffff:
                return str(device)
        except OSError:
            continue
    # USB adapters and systems without readable kernel CEC use libCEC discovery.
    return None


class RemoteInput:
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.lock = threading.Lock()
        self.boot = secrets.token_hex(12)
        self.sequence = 0
        self.events = deque(maxlen=32)
        self.pending = deque(maxlen=32)
        self.held = None
        self.last = None
        self.owner = None
        self.lease_until = 0

    def callback(self, code, duration):
        with self.lock:
            if duration:
                if self.held == code:
                    self.held = None
                return 0
            if self.held == code:
                return 0
            self.held = code
            key = KEYS.get(code)
            self.last = {'key': LABELS.get(key, 'Nicht zugeordnet'), 'code': hex(code),
                         'at': datetime.now(timezone.utc).isoformat(), 'supported': key is not None}
            if key:
                self.pending.append((self.clock(), key))
        return 0

    def take(self):
        with self.lock:
            now = self.clock()
            result = [key for at, key in self.pending if now - at < 1.5]
            self.pending.clear()
            return result

    def publish(self, key):
        with self.lock:
            self.sequence += 1
            self.events.append({'id': self.sequence, 'key': key, 'at': self.clock()})

    def poll(self, body):
        client, cursor = body.get('client'), body.get('cursor')
        if not isinstance(client, str) or not 16 <= len(client) <= 80:
            raise ValueError('Ungültiger TV-Empfänger')
        if cursor is not None and (type(cursor) is not int or cursor < 0):
            raise ValueError('Ungültiger Tastencursor')
        with self.lock:
            now = self.clock()
            result = {'boot': self.boot, 'cursor': self.sequence, 'events': []}
            if self.owner != client:
                if now < self.lease_until:
                    return result | {'waiting': True}
                self.owner = client
                self.lease_until = now + 2
                return result  # New tabs never replay earlier keypresses.
            self.lease_until = now + 2
            if body.get('boot') != self.boot or cursor is None or cursor > self.sequence:
                return result
            result['events'] = [{'id': e['id'], 'key': e['key']} for e in self.events
                                if e['id'] > cursor and now - e['at'] < 1.5]
            return result

    def reset(self):
        with self.lock:
            self.held = None
            self.pending.clear()
            self.events.clear()
            self.boot = secrets.token_hex(12)
            self.owner = None
            self.lease_until = 0

    def diagnostic(self):
        with self.lock:
            return {'last_key': dict(self.last) if self.last else None,
                    'receiver_active': bool(self.owner and self.clock() < self.lease_until)}


class CecBridge:
    """Keep cec-client open; isolate native libCEC from the Python/GPIO service."""
    def __init__(self, remote, factory=subprocess.Popen, adapter_probe=connected_adapter):
        self.remote, self.factory = remote, factory
        self.adapter_probe = adapter_probe
        self.adapter = None
        self.io = threading.Lock()
        self.stop = threading.Event()
        self.process = None
        self.connected = False
        self.addresses = set()
        self.message = 'CEC noch nicht verbunden.'
        self.thread = None

    def line(self, line):
        # libCEC logs only received frames with >>; never accept our own TX.
        if 'logical address(es)' in line:
            addresses = re.findall(r'\(([0-9]{1,2})\)', line.split('logical address(es)', 1)[1])
            self.addresses = {int(n) for n in addresses if int(n) in (4, 8, 11)}
        lower = line.lower()
        if ('connection opened' in lower and 'connection opened: 0' not in lower) or 'waiting for input' in lower:
            self.connected = True
            self.message = 'CEC-Adapter verbunden. Tasten am TV prüfen.'
        if any(text in lower for text in ('connection lost', 'failed to open', 'unable to open',
                                          'connection opened: 0', 'autodetect failed')):
            self.connected = False
            self.addresses.clear()
            self.remote.reset()
            self.message = 'CEC-Verbindung fehlt. HDMI, TV und Geräteberechtigung prüfen.'
        if 'not acked' in lower or 'transmit failed' in lower:
            self.message = 'CEC-Befehl nicht bestätigt. HDMI und Fernseher prüfen.'
        frame = re.search(r'>>\s+([0-9a-f]{2}(?::[0-9a-f]{2})+)\s*$', line.lower())
        if not frame or not self.connected:
            return
        data = bytes.fromhex(frame[1].replace(':', ''))
        # Receive only keys directed from the TV to this client's own address.
        if data[0] >> 4 != 0 or data[0] & 15 not in self.addresses:
            return
        if len(data) == 3 and data[1] == 0x44:
            self.remote.callback(data[2], 0)
        elif len(data) == 2 and data[1] == 0x45:
            with self.remote.lock:
                held = self.remote.held
            if held is not None:
                self.remote.callback(held, 1)

    def command(self, command):
        text = {'on': 'on 0\nas\n', 'off': 'standby 0\n'}.get(command)
        if text is None:
            raise ValueError('Unbekannter CEC-Befehl')
        with self.io:
            if not self.connected or self.process is None or self.process.poll() is not None:
                raise RuntimeError('CEC nicht verbunden')
            try:
                self.process.stdin.write(text)
                self.process.stdin.flush()
            except (OSError, ValueError):
                self.connected = False
                raise RuntimeError('CEC-Befehl konnte nicht übergeben werden')
        # This acknowledges delivery to cec-client, not TV power or HDMI ACK.
        self.message = 'CEC-Befehl übergeben. Reaktion am Fernseher prüfen.'

    def snapshot(self):
        alive = self.process is not None and self.process.poll() is None
        return {'connected': bool(self.connected and alive), 'message': self.message,
                'adapter': self.adapter} | self.remote.diagnostic()

    def terminate(self):
        with self.io:
            process, self.process = self.process, None
            self.connected = False
            self.addresses.clear()
            self.remote.reset()
            if process is None:
                return
            # No `q`, standby or wake command on service stop/restart.
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=2)
            process.stdin.close()
            process.stdout.close()

    def run(self):
        while not self.stop.is_set():
            try:
                with self.io:
                    self.adapter = self.adapter_probe()
                    args = ['cec-client', '-d', '13', '-t', 'p', '-o', 'Kamerablick', '-aw', '0']
                    if self.adapter:
                        args.append(self.adapter)
                    self.process = self.factory(args,
                        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                        text=True, bufsize=1)
                    process = self.process
                # No shell, raw logs or credentials are exposed through the API.
                opened_at = time.monotonic()
                next_probe = opened_at + 5
                buffer = b''
                with selectors.DefaultSelector() as selector:
                    selector.register(process.stdout, selectors.EVENT_READ)
                    while not self.stop.is_set() and process.poll() is None:
                        if not self.connected and time.monotonic() - opened_at > 20:
                            break
                        if time.monotonic() >= next_probe:
                            next_probe = time.monotonic() + 5
                            adapter = self.adapter_probe()
                            if adapter is not None and adapter != self.adapter:
                                break
                        if not selector.select(.2):
                            continue
                        chunk = os.read(process.stdout.fileno(), 4096)
                        if not chunk:
                            break
                        buffer += chunk
                        while b'\n' in buffer:
                            line, buffer = buffer.split(b'\n', 1)
                            self.line(line.decode('utf-8', errors='replace').strip())
                        if len(buffer) > 32768:
                            buffer = b''
                if not self.stop.is_set():
                    self.message = 'CEC-Prozess beendet. Verbindung wird erneut versucht.'
            except (OSError, ValueError):
                self.message = 'CEC nicht erreichbar. cec-utils, HDMI und Geräteberechtigung prüfen.'
            finally:
                self.terminate()
            self.stop.wait(5)

    def start(self):
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def close(self):
        self.stop.set()
        # Termination wakes the stdout reader; do not close its pipe concurrently.
        with self.io:
            process = self.process
            if process is not None and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
        if self.thread:
            self.thread.join(timeout=5)
        else:
            self.terminate()
