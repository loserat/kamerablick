import hashlib
import http.server
import json
from pathlib import Path
import shutil
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

PI = Path(__file__).parents[1] / 'pi'
sys.path.insert(0, str(PI))
import doctor
import install


class Diagnosis(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve() / 'project'
        self.home = Path(self.temp.name).resolve() / 'home'
        (self.root / 'pi').mkdir(parents=True)
        for name in install.RUNTIME_FILES:
            shutil.copy(PI / name, self.root / 'pi' / name)
        self.image = 'ghcr.io/loserat/kamerablick:v1.0.0'
        self.settings = install.prepare(self.root, self.home, image=self.image)

    def command(self, args, root):
        self.assertEqual(root, self.root)
        if args[0] == 'systemctl':
            self.assertEqual(args[:3], ['systemctl', '--user', 'show'])
            return 'active'
        if args[0] == 'loginctl':
            return 'yes'
        self.assertEqual(args[:3], ['docker', 'compose', 'ps'])
        return json.dumps([{'State': 'running', 'Health': 'healthy', 'Image': self.image}])

    def network(self, port, path, token='', body=None):
        if port == 8088:
            self.assertEqual((path, token, body), ('/healthz', '', None))
            return {'ok': True}
        self.assertEqual(token, self.settings['AGENT_TOKEN'])
        if port == 8091:
            self.assertEqual((path, body), ('/action', {'action': 'status'}))
            return {'active': False, 'gpio_pin': 17, 'message': self.settings['DASHBOARD_PASSWORD']}
        self.assertEqual((port, path, body), (8093, '/healthz', None))
        return {'protocol': 1, 'available': True, 'persistent': True,
            'instance': hashlib.sha256(str(self.root).encode()).hexdigest(),
            'runtime': (self.root / '.runtime/current').resolve().name, 'current_version': 'v1.0.0'}

    def run_diagnosis(self):
        with patch.object(doctor, 'command', side_effect=self.command), patch.object(doctor, 'local_json', side_effect=self.network):
            return doctor.diagnose(self.root, self.home)

    def test_read_only_report_checks_live_services_without_exposing_credentials(self):
        files = {p: (p.read_bytes(), p.stat().st_mode) for p in Path(self.temp.name).rglob('*') if p.is_file()}
        result = self.run_diagnosis()
        self.assertTrue(all(c['status'] == 'ok' for c in result['checks']))
        self.assertTrue(result['read_only'])
        self.assertFalse(result['hardware_verified'])
        self.assertNotIn(self.settings['DASHBOARD_PASSWORD'], json.dumps(result))
        self.assertNotIn(self.settings['AGENT_TOKEN'], json.dumps(result))
        self.assertEqual(files, {p: (p.read_bytes(), p.stat().st_mode) for p in Path(self.temp.name).rglob('*') if p.is_file()})

    def test_legacy_environment_file_and_mismatched_key_are_identified(self):
        unit = self.home / '.config/systemd/user/oma-tv-maintenance.service'
        unit.write_text(unit.read_text().replace('EnvironmentFile=', 'EnvironmentFile="'))
        env = self.home / '.config/oma-tv/agent.env'
        env.write_text('AGENT_TOKEN=' + 'z' * 32 + '\n')
        result = self.run_diagnosis()
        checks = {c['id']: c['status'] for c in result['checks']}
        self.assertEqual(checks['host_key'], 'fail')
        self.assertEqual(checks['oma-tv-maintenance.service:env'], 'fail')
        self.assertEqual(checks['maintenance'], 'fail')
        self.assertEqual(checks['agent'], 'fail')

    def test_malformed_missing_and_private_settings_do_not_leak_error_text(self):
        (self.root / '.env').write_text('invalid private password\n')
        with patch.object(doctor, 'command', return_value=None), patch.object(doctor, 'local_json', return_value={}):
            result = doctor.diagnose(self.root, self.home)
        self.assertNotIn('private password', json.dumps(result))
        self.assertEqual(result['checks'][0]['status'], 'fail')

    def test_local_probes_never_follow_redirects_with_the_host_key(self):
        paths = []
        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_GET(self):
                paths.append(self.path)
                self.send_response(302)
                self.send_header('Location', '/must-not-follow')
                self.end_headers()
        httpd = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            with self.assertRaises(OSError):
                doctor.local_json(httpd.server_port, '/healthz', 'host-key-only')
            self.assertEqual(paths, ['/healthz'])
        finally:
            httpd.shutdown()
            httpd.server_close()
