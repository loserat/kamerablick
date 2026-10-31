"""Start the local TV browser only after the dashboard is ready."""
import json
import os
from pathlib import Path
import shutil
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
    result = subprocess.run([browser, '--user-data-dir=' + str(profile), '--kiosk',
        '--no-first-run', '--no-default-browser-check', '--disable-session-crashed-bubble',
        base + '/tv#access=' + quote(access['token'], safe='') + '&receiver=' + quote(access['receiver'], safe='')],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    raise SystemExit(result.returncode)


if __name__ == '__main__':
    main()
