"""Published stable Kamerablick releases; no user-supplied download locations."""
import http.client
import json
import re
import ssl
import threading
import time

REPOSITORY = 'loserat/kamerablick'
IMAGE = 'ghcr.io/' + REPOSITORY
_cache = {}
_lock = threading.Lock()


def version(value):
    if not isinstance(value, str) or not re.fullmatch(r'v(?:0|[1-9][0-9]{0,7})\.(?:0|[1-9][0-9]{0,7})\.(?:0|[1-9][0-9]{0,7})', value):
        raise ValueError('Eine veröffentlichte stabile Version wie v0.1.4 auswählen.')
    return tuple(int(part) for part in value[1:].split('.'))


def newer(candidate, current):
    return version(candidate) > version(current)


def release(tag=None, *, refresh=False):
    if tag is not None:
        version(tag)
    key = tag or 'latest'
    with _lock:
        cached = _cache.get(key)
        if not refresh and cached and cached[0] > time.monotonic():
            return dict(cached[1])
    path = '/repos/' + REPOSITORY + '/releases/' + ('tags/' + tag if tag else 'latest')
    connection = http.client.HTTPSConnection('api.github.com', timeout=8, context=ssl.create_default_context())
    try:
        connection.request('GET', path, headers={'Accept': 'application/vnd.github+json', 'User-Agent': 'Kamerablick-Updater'})
        response = connection.getresponse()
        raw = response.read(1024 * 1024 + 1)
        if response.status != 200 or len(raw) > 1024 * 1024:
            raise ValueError('GitHub-Version nicht erreichbar. Internetverbindung prüfen und später erneut versuchen.')
        data = json.loads(raw)
        actual = data.get('tag_name')
        version(actual)
        if data.get('draft') or data.get('prerelease') or (tag is not None and actual != tag):
            raise ValueError('Diese Version ist kein freigegebenes stabiles Release.')
        result = {'version': actual, 'name': str(data.get('name') or actual)[:200],
            'notes': str(data.get('body') or '')[:20000], 'published_at': data.get('published_at'),
            'url': 'https://github.com/' + REPOSITORY + '/releases/tag/' + actual}
    except (OSError, http.client.HTTPException, KeyError, TypeError, json.JSONDecodeError):
        raise ValueError('GitHub-Version konnte nicht geprüft werden. Verbindung und Release prüfen.') from None
    finally:
        connection.close()
    with _lock:
        _cache[key] = (time.monotonic() + 300, result)
    return dict(result)
