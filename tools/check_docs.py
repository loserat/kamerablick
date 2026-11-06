"""Check local documentation, release references and verification metadata offline."""
from html import unescape
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sys
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.targets = []

    def handle_starttag(self, tag, attrs):
        for name, value in attrs:
            if value and name in ('src', 'href'):
                self.targets.append(value)


def prose(text):
    return re.sub(r'^```[^\n]*\n.*?^```[^\n]*$', '', text, flags=re.M | re.S)


def anchors(text):
    result = set()
    counts = {}
    for heading in re.findall(r'^#{1,6}\s+(.+?)\s*#*\s*$', prose(text), re.M):
        heading = re.sub(r'<[^>]*>', '', unescape(heading)).lower()
        slug = re.sub(r'[^\w\- ]', '', heading).replace(' ', '-')
        index = counts.get(slug, 0)
        counts[slug] = index + 1
        result.add(slug + ('-' + str(index) if index else ''))
    return result


def check():
    failures = []
    documents = [*ROOT.glob('*.md'), *sorted((ROOT / 'docs').rglob('*.md'))]
    links = 0
    for document in documents:
        text = prose(document.read_text())
        html = Links()
        html.feed(text)
        targets = re.findall(r'!?\[[^\]\n]*\]\(([^)\n]+)\)', text) + html.targets
        for value in targets:
            target = urlsplit(unescape(value.strip('<>')))
            if target.scheme or target.netloc:
                continue
            destination = (document.parent / unquote(target.path)).resolve() if target.path else document
            links += 1
            if not destination.is_relative_to(ROOT):
                failures.append(f'{document.relative_to(ROOT)}: link leaves repository: {value}')
            elif not destination.exists():
                failures.append(f'{document.relative_to(ROOT)}: missing target: {value}')
            elif target.fragment and destination.suffix == '.md':
                if unquote(target.fragment) not in anchors(destination.read_text()):
                    failures.append(f'{document.relative_to(ROOT)}: missing heading: {value}')

    readme = (ROOT / 'README.md').read_text()
    compose = (ROOT / 'compose.home-test.yaml').read_text()
    version = re.search(r'ghcr[.]io/loserat/kamerablick:(v\d+[.]\d+[.]\d+)', compose)
    if not version:
        failures.append('compose.home-test.yaml: missing versioned image')
    else:
        current = version.group(1)
        for expected in ('Version-' + current + '-', '--branch ' + current,
                         'ghcr.io/loserat/kamerablick:' + current):
            if expected not in readme:
                failures.append('README.md: missing current release reference: ' + expected)
        if 'APP_VERSION: ' + current not in compose:
            failures.append('compose.home-test.yaml: image and app version differ')
        records = sorted((ROOT / 'docs/verification').glob('v*.json'))
        if not records:
            failures.append('Missing release verification summaries')
        for record in records:
            evidence = json.loads(record.read_text())
            if evidence.get('release') != record.stem or not evidence.get('summary_only'):
                failures.append('Invalid release verification scope: ' + record.stem)
            if not re.fullmatch('[0-9a-f]{40}', evidence.get('release_source_commit', '')):
                failures.append('Missing exact verified release commit: ' + record.stem)
            if not evidence.get('not_yet_device_verified'):
                failures.append('Verification summary must state its remaining device checks: ' + record.stem)
        if records and current not in {record.stem for record in records}:
            print(f'Hinweis: Für {current} ist noch kein abgeschlossener Geräteprüfstand erfasst.')
    if failures:
        print('\n'.join(failures), file=sys.stderr)
        return 1
    print(f'{len(documents)} Dokumente und {links} lokale Verweise geprüft; Release und Prüfstand konsistent.')
    return 0


if __name__ == '__main__':
    raise SystemExit(check())
