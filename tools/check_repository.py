"""Reject private state, generated artifacts and obvious key material before publishing."""
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
PRIVATE_DIRECTORIES = {'data', 'backups', '.runtime', '.maintenance', '.venv', '.test-env',
                       '__pycache__', '.pytest_cache', 'Pruefberichte', 'test-results',
                       'playwright-report', 'chromium-kamerablick'}
PRIVATE_NAMES = {'config.json', 'protect.json', 'dashboard-auth.json', 'manual-cameras.json',
                 'telemetry.json', 'tv-access.json', 'tv-receiver.json', 'update-state.json',
                 'agent.env', '.install.json', '.update.lock', 'image-index.json', 'release-notes.md'}
GENERATED_SUFFIXES = ('.pyc', '.log', '.pem', '.key', '.p12', '.pfx', '.sqlite', '.sqlite3',
                      '.db', '.zip', '.tar', '.tar.gz', '.tgz')
SIGNATURES = {
    'private key': rb'-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----',
    'GitHub token': rb'\b(?:gh[pousr]_|github_pat_)[A-Za-z0-9_]{20,}',
}
DOCKER_INPUT_RULES = {'!Dockerfile', '!requirements.txt', '!app/*.py',
                      '!app/static/*.js', '!app/static/*.css', '!app/static/*.html',
                      '!app/static/*.svg', '!app/static/*.png', '!pi/*.py'}


def check():
    result = subprocess.run(['git', 'ls-files', '-z', '--cached', '--others', '--exclude-standard'],
                            cwd=ROOT, capture_output=True, check=True)
    files = sorted(set(result.stdout.decode().strip('\0').split('\0')))
    failures = []
    total = 0
    for name in files:
        if not name:
            continue
        path = Path(name)
        private_env = path.name == '.env' or path.name.startswith('.env.') and path.name != '.env.example'
        if (PRIVATE_DIRECTORIES.intersection(path.parts) or path.name in PRIVATE_NAMES or private_env
                or name.endswith(GENERATED_SUFFIXES)):
            failures.append(f'Nicht veröffentlichen: {name}')
        source = ROOT / path
        if source.is_symlink():
            failures.append(f'Symbolischen Link vor Veröffentlichung prüfen: {name}')
            continue
        if not source.is_file():
            continue
        content = source.read_bytes()
        total += len(content)
        for label, signature in SIGNATURES.items():
            if re.search(signature, content):
                failures.append(f'{label} erkannt: {name} (Wert nicht ausgegeben)')
    example = (ROOT / '.env.example').read_text()
    for key in ('DASHBOARD_PASSWORD', 'AGENT_TOKEN'):
        if not re.search(r'^' + key + r'=BITTE_[A-Z_]+$', example, re.M):
            failures.append(f'.env.example: {key} muss ein eindeutiger Platzhalter sein')
    rules = [line.strip() for line in (ROOT / '.dockerignore').read_text().splitlines()
             if line.strip() and not line.lstrip().startswith('#')]
    if not rules or rules[0] != '**' or set(rules[1:]) != DOCKER_INPUT_RULES:
        failures.append('.dockerignore muss ausschließlich die benötigten Quelldateien freigeben')
    if failures:
        print('\n'.join(failures), file=sys.stderr)
        return 1
    print(f'{len(files)} Projektdateien geprüft ({total} Bytes); keine gesperrten Dateien oder Schlüsselsignaturen.')
    return 0


if __name__ == '__main__':
    raise SystemExit(check())
