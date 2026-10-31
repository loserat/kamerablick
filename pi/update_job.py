"""Detached browser-update worker; survives restarts of the dashboard and Pi UI."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import re

from install import project_root
from maintenance import Store
import release_info
import update


def verify_image(image):
    container = update.run(['docker','create',image],capture=True).stdout.strip()
    try:
        result=update.run(['docker','inspect','--format','{{json .Config.Labels}}',container],capture=True)
        labels=json.loads(result.stdout)
        if (not isinstance(labels,dict) or labels.get('org.opencontainers.image.source')!='https://github.com/'+release_info.REPOSITORY
                or labels.get('org.opencontainers.image.version')!=image.rsplit(':',1)[1]):
            raise ValueError('Container gehört nicht zur ausgewählten Kamerablick-Version.')
    finally:
        update.run(['docker','rm',container],capture=True,allowed=True)


def execute(root, job_id, *, recover=False):
    root = Path(root).resolve()
    store = Store(root)
    job = store.read()
    if not re.fullmatch(r'[a-f0-9]{24}', job_id) or not job or job.get('id') != job_id:
        raise ValueError('Unbekannter Wartungsauftrag.')
    previous_root = update.ROOT
    update.ROOT = root
    try:
        with open(root / '.update.lock', 'a') as handle:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if recover:
                store.phase('recovering')
                update.recover(progress=store.phase)
                store.phase('rolled_back')
            else:
                store.phase('checking')
                tag = job['version']
                release_info.release(tag, refresh=True)
                update.recover(progress=store.phase)
                update.update(release_info.IMAGE + ':' + tag, progress=store.phase, verify=verify_image)
                store.phase('complete')
    except Exception:
        path = root / 'backups/update-state.json'
        state = json.loads(path.read_text()) if path.exists() else {}
        last_phase = (store.read() or {}).get('phase')
        restoring = last_phase in ('rolling_back','recovering')
        phase = ('rolled_back' if restoring and state.get('phase') == 'rolled_back' else
            'recovery_failed' if state.get('phase') in ('applying', 'rollback_failed') and last_phase in ('installing','verifying','rolling_back','recovering') else 'failed')
        store.phase(phase)
        return False
    finally:
        update.ROOT = previous_root
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=project_root(__file__))
    parser.add_argument('--job', required=True)
    parser.add_argument('--recover', action='store_true')
    args = parser.parse_args()
    os.umask(0o077)
    raise SystemExit(0 if execute(args.root, args.job, recover=args.recover) else 1)


if __name__ == '__main__':
    main()
