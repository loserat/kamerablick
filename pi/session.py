"""XDG autostart bridge: import this desktop's environment before user services."""
import os
from pathlib import Path
import subprocess
import time

NAMES = ('DISPLAY', 'WAYLAND_DISPLAY', 'XDG_RUNTIME_DIR', 'DBUS_SESSION_BUS_ADDRESS', 'XAUTHORITY')


def display_socket(env):
    wayland = env.get('WAYLAND_DISPLAY')
    if wayland:
        path = Path(wayland)
        return path if path.is_absolute() else Path(env.get('XDG_RUNTIME_DIR', '/run/user/' + str(os.getuid()))) / path
    display = env.get('DISPLAY', '')
    if display.startswith(':'):
        return Path('/tmp/.X11-unix/X' + display[1:].split('.')[0])
    raise ValueError('Keine lokale grafische Sitzung gefunden')


def main():
    root = Path(__file__).resolve().parents[3]
    # A source checkout is never a supported service location: installer uses .runtime/releases/ID.
    sock = display_socket(os.environ)
    if not sock.exists():
        raise SystemExit('Der Bildschirmdienst ist noch nicht bereit.')
    subprocess.run(['systemctl', '--user', 'import-environment', *[key for key in NAMES if os.getenv(key)]], check=True)
    recovery = root / 'pi/update.py'
    state = root / 'backups/update-state.json'
    if recovery.exists() and state.exists():
        # The updater decides whether an interrupted operation actually needs recovery.
        result = subprocess.run(['/usr/bin/python3', str(recovery), '--recover'])
        if result.returncode:
            raise SystemExit('Update-Wiederherstellung fehlgeschlagen. Wartungszugang prüfen.')
    subprocess.run(['systemctl', '--user', 'start', 'oma-tv-session.target'], check=True)
    try:
        while sock.exists():
            time.sleep(3)
    finally:
        subprocess.run(['systemctl', '--user', 'stop', 'oma-tv-session.target'])


if __name__ == '__main__':
    main()
