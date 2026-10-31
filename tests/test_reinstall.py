"""Data-preserving cold reinstall, including an interrupted legacy transaction."""
import fcntl
import json
from pathlib import Path
import shutil
from subprocess import CompletedProcess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1] / 'pi'))
import install
import reinstall
import update


class Reinstall(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'project'
        self.home = Path(self.temp.name) / 'home'
        (self.root / 'pi').mkdir(parents=True)
        for name in install.RUNTIME_FILES:
            shutil.copy(Path(__file__).parents[1] / 'pi' / name, self.root / 'pi' / name)
        install.prepare(self.root, self.home, image='ghcr.io/loserat/kamerablick:v0.1.2')
        self.environment = (self.root / '.env').read_text()
        self.state = self.root / 'backups/update-state.json'
        install.atomic_write(self.state, json.dumps({'phase': 'rollback_failed', 'private': 'old recovery evidence'}))
        self.job = self.root / '.maintenance/job.json'
        install.atomic_write(self.job, json.dumps({'phase': 'recovery_failed', 'watch_hash': 'private-hash'}))
        install.atomic_write(self.home / '.config/oma-tv/config.json', json.dumps({'gpio_pin': 17}))
        self.calls = []
        self.image = 'ghcr.io/loserat/kamerablick:v0.1.4'
        self.patch(install, 'preflight', return_value=[{'ok': True}])
        self.patch(reinstall.release_info, 'release', return_value={'version': 'v0.1.4'})
        self.verify = self.patch(reinstall, 'verify_image')
        self.patch(update, 'run', side_effect=self.command)
        self.install = self.patch(install, '_install_project', side_effect=self.reconfigure)
        self.health = self.patch(update, 'wait_healthy')

    def patch(self, target, name, **kwargs):
        change = patch.object(target, name, **kwargs)
        self.addCleanup(change.stop)
        return change.start()

    def command(self, args, **kwargs):
        self.calls.append(args)
        output = ''
        if args[:2] == ['docker', 'create']:
            output = 'staging'
        elif args[:2] == ['docker', 'cp']:
            shutil.copytree(self.root / 'pi', args[-1])
        elif args[:3] == ['docker', 'compose', 'ps']:
            output = 'existing-dashboard'
        elif args[:3] == ['docker', 'compose', 'exec']:
            output = json.dumps({'config.json': '{"camera_name":"Existing camera"}', 'protect.json': '{"api_key":"private-key"}'})
        elif args[:2] == ['docker', 'inspect']:
            output = 'sha256:actual-previous-image'
        elif args[:3] == ['systemctl', '--user', 'is-active']:
            return CompletedProcess(args, 3, '', '')
        elif args[:3] == ['systemctl', '--user', 'show']:
            output = 'loaded'
        return CompletedProcess(args, 0, output, '')

    def reconfigure(self, root, home, image):
        self.assertFalse(self.state.exists())
        self.assertFalse(self.job.exists())
        with open(root / '.update.lock', 'a') as handle:
            with self.assertRaises(BlockingIOError):
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        install.prepare(root, home, image=image)

    def test_keeps_password_settings_evidence_and_actual_previous_image(self):
        before_root = update.ROOT
        backup = reinstall.reinstall(self.root, self.home, self.image)
        self.assertEqual(update.ROOT, before_root)
        old = install.read_env(backup / 'environment')
        new = install.read_env(self.root / '.env')
        for key in ('DASHBOARD_PASSWORD', 'AGENT_TOKEN', 'BIND', 'PORT'):
            self.assertEqual(new[key], old[key])
        self.assertEqual(new['APP_VERSION'], 'v0.1.4')
        self.assertEqual(new['OMA_TV_IMAGE'], self.image)
        self.assertEqual(json.loads((backup / 'previous-update-state.json').read_text())['phase'], 'rollback_failed')
        self.assertEqual(json.loads((backup / 'previous-job.json').read_text())['watch_hash'], 'private-hash')
        self.assertIn('private-key', (backup / 'data.json').read_text())
        self.assertEqual(backup.stat().st_mode & 0o777, 0o700)
        for file in backup.rglob('*'):
            if file.is_file(): self.assertEqual(file.stat().st_mode & 0o777, 0o600)
        self.assertEqual(json.loads((backup / 'reinstall.json').read_text())['phase'], 'complete')
        self.assertTrue(any(args[:3] == ['docker', 'tag', 'sha256:actual-previous-image'] for args in self.calls))
        self.assertFalse(any('down' in args or 'prune' in args for args in self.calls))
        self.health.assert_called_once_with(True)

    def test_active_update_is_never_overlapped(self):
        with open(self.root / '.update.lock', 'a') as handle:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaisesRegex(ValueError, 'läuft noch'):
                reinstall.reinstall(self.root, self.home, self.image)
        self.assertEqual(self.calls, [])
        self.assertEqual((self.root / '.env').read_text(), self.environment)

    def test_wrong_image_is_rejected_before_stop_or_configuration_changes(self):
        self.verify.side_effect = ValueError('Wrong image')
        with self.assertRaisesRegex(ValueError, 'Wrong image'):
            reinstall.reinstall(self.root, self.home, self.image)
        self.assertEqual((self.root / '.env').read_text(), self.environment)
        self.assertTrue(self.state.exists())
        self.assertFalse(any(args[:3] == ['systemctl', '--user', 'stop'] for args in self.calls))

    def test_failed_start_never_claims_completed_and_retains_backup(self):
        self.health.side_effect = RuntimeError('start check failed')
        with self.assertRaisesRegex(ValueError, 'noch nicht erfolgreich bestätigt'):
            reinstall.reinstall(self.root, self.home, self.image)
        backup = next((self.root / 'backups').glob('neuinstallation-*'))
        self.assertTrue((backup / 'previous-update-state.json').exists())
        self.assertIn('private-key', (backup / 'data.json').read_text())
        self.assertEqual(json.loads((backup / 'reinstall.json').read_text())['phase'], 'installing')

    def test_foreign_service_is_not_replaced(self):
        install.atomic_write(self.home / '.config/systemd/user/oma-tv-agent.service', '[Service]\nCustom=yes\n')
        with self.assertRaisesRegex(ValueError, 'Eigene Datei'):
            reinstall.reinstall(self.root, self.home, self.image)
        self.assertEqual(self.calls, [])

    def test_foreign_source_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'offizielle'):
            reinstall.reinstall(self.root, self.home, 'ghcr.io/another/repository:v0.1.4')
        self.assertEqual(self.calls, [])


if __name__ == '__main__':
    unittest.main()
