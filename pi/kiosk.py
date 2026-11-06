"""Start the local TV browser only after the dashboard is ready."""
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import time
import urllib.request
from urllib.parse import urlsplit, quote


def local_base():
    port = int(os.getenv('PORT', '8088'))
    if not 1 <= port <= 65535:
        raise ValueError('Ungültiger Dashboard-Port')
    return 'http://127.0.0.1:' + str(port)


def provision(base, token):
    if len(token) < 24:
        raise ValueError('Gemeinsamer Pi-Schlüssel fehlt')
    req = urllib.request.Request(base + '/api/tv/provision', data=b'{}',
        headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=10) as response:
        access = json.load(response)
    if not all(isinstance(access.get(key), str) and access[key] for key in ('token','receiver')):
        raise ValueError('TV-Freigabe fehlt')
    return access


def run_browser(args):
    # Chromium can move itself into a separate systemd scope. Terminate our own
    # child explicitly so stopping this service also closes its TV window.
    stopping = False
    process = None

    def stop(signum, frame):
        nonlocal stopping
        stopping = True

    previous = {s: signal.signal(s, stop) for s in (signal.SIGTERM, signal.SIGINT)}
    try:
        process = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        while not stopping:
            try:
                return process.wait(timeout=.5)
            except subprocess.TimeoutExpired:
                pass
        return 0
    finally:
        try:
            if process is not None and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=2)
        finally:
            for signum, handler in previous.items():
                signal.signal(signum, handler)


def main():
    base = local_base()
    browser = shutil.which('chromium') or shutil.which('chromium-browser')
    if not browser:
        raise SystemExit('Chromium fehlt. Pakete und Installation prüfen.')
    while True:
        try:
            access = provision(base, os.getenv('AGENT_TOKEN', ''))
            break
        except (OSError, ValueError, KeyError):
            print('Warte auf das lokale Dashboard …', flush=True)
            time.sleep(5)
    profile = Path.home() / '.config/chromium-kamerablick'
    # Credentials appear neither in terminal output nor in journal error messages.
    # This dedicated TV profile uses local pairing, never saved account passwords.
    # Avoid an interactive desktop keyring prompt during unattended startup.
    result = run_browser([browser, '--user-data-dir=' + str(profile), '--kiosk', '--password-store=basic',
        '--disable-features=Translate',
        '--no-first-run', '--no-default-browser-check', '--disable-session-crashed-bubble',
        base + '/tv#access=' + quote(access['token'], safe='') + '&receiver=' + quote(access['receiver'], safe='')])
    raise SystemExit(result)


if __name__ == '__main__':
    main()
