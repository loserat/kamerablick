import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch
from subprocess import CompletedProcess

PI = Path(__file__).parents[1] / 'pi'
sys.path.insert(0, str(PI))
import install
import kiosk
import session


class Installation(unittest.TestCase):
    def test_home_test_config_is_never_silently_used_for_hardware(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)/'project';root.mkdir()
            (root/'.env').write_text('DASHBOARD_PASSWORD=existing-private-password\nAGENT_TOKEN='+'a'*32+'\nDEMO_MODE=false\nHOME_TEST_MODE=true\n')
            with self.assertRaisesRegex(ValueError,'Heimtest'):
                install.prepare(root,Path(temporary)/'home')
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / 'project'
        self.home = Path(self.temp.name) / 'desktop-user'
        (self.root / 'pi').mkdir(parents=True)
        for name in install.RUNTIME_FILES:
            shutil.copy(PI / name, self.root / 'pi' / name)
    def tearDown(self): self.temp.cleanup()
    def test_repeat_preserves_secrets_and_runtime(self):
        first = install.prepare(self.root, self.home)
        env = (self.root / '.env').read_bytes()
        target = (self.root / '.runtime/current').resolve()
        second = install.prepare(self.root, self.home)
        self.assertEqual(first['AGENT_TOKEN'], second['AGENT_TOKEN'])
        self.assertEqual(env, (self.root / '.env').read_bytes())
        self.assertEqual(target, (self.root / '.runtime/current').resolve())
        self.assertGreaterEqual(len(first['AGENT_TOKEN']), 24)
        self.assertEqual((self.root / '.env').stat().st_mode & 0o777, 0o600)
        self.assertEqual((self.home / '.config/oma-tv/agent.env').stat().st_mode & 0o777, 0o600)
        self.assertIn('PartOf=oma-tv-session.target', (self.home / '.config/systemd/user/oma-tv-kiosk.service').read_text())
    def test_foreign_autostart_not_overwritten(self):
        file = self.home / '.config/autostart/kamerablick.desktop'
        file.parent.mkdir(parents=True);file.write_text('existing desktop entry')
        with self.assertRaises(ValueError): install.prepare(self.root, self.home)
        self.assertEqual(file.read_text(), 'existing desktop entry')
        self.assertFalse((self.root / '.env').exists())
    def test_placeholder_and_demo_settings_are_not_silently_changed(self):
        path = self.root / '.env'
        for text in ('DASHBOARD_PASSWORD=BITTE_AENDERN\nAGENT_TOKEN=abc\n',
                     'DASHBOARD_PASSWORD=test\nAGENT_TOKEN='+'a'*32+'\nDEMO_MODE=true\n'):
            path.write_text(text)
            with self.assertRaises(ValueError): install.prepare(self.root, self.home)
            self.assertEqual(path.read_text(), text)
            self.assertFalse((self.home / '.config/autostart/kamerablick.desktop').exists())
    def test_existing_quoted_password_is_preserved(self):
        content = "DASHBOARD_PASSWORD='pass with $ and # spaces'\nAGENT_TOKEN="+'a'*32+'\nDEMO_MODE=false\n'
        (self.root / '.env').write_text(content)
        values = install.prepare(self.root, self.home)
        self.assertEqual(values['DASHBOARD_PASSWORD'], 'pass with $ and # spaces')
        self.assertEqual((self.root / '.env').read_text(), content)
    def test_kiosk_provision_rejects_missing_shared_key(self):
        with patch.object(kiosk.urllib.request, 'urlopen') as network:
            with self.assertRaises(ValueError): kiosk.provision('http://127.0.0.1:8088','short')
            network.assert_not_called()
    def test_desktop_socket_detection(self):
        self.assertEqual(session.display_socket({'WAYLAND_DISPLAY':'wayland-1','XDG_RUNTIME_DIR':'/run/user/1000'}),Path('/run/user/1000/wayland-1'))
        self.assertEqual(session.display_socket({'DISPLAY':':0.0'}),Path('/tmp/.X11-unix/X0'))
        with self.assertRaises(ValueError): session.display_socket({})
    def test_runtime_rejects_escaping_paths_and_symlinks(self):
        with self.assertRaises(ValueError):
            install.runtime_release(self.root,self.root/'pi',('agent.py','kiosk.py','session.py','../outside.py'))
        target=self.root/'outside.py';target.write_text('VALUE=42\n')
        (self.root/'pi/linked.py').symlink_to(target)
        with self.assertRaises(ValueError):
            install.runtime_release(self.root,self.root/'pi',('agent.py','kiosk.py','session.py','linked.py'))
    def test_registry_install_uses_image_runtime_without_local_build(self):
        image='ghcr.io/example/kamerablick:v1.0.0'
        staged=self.root/'image-runtime';staged.mkdir()
        for name in install.RUNTIME_FILES:
            (staged/name).write_text((PI/name).read_text()+'\n# selected image version\n')
        def command(args,**kwargs):
            if args[:2]==['docker','create']:return CompletedProcess(args,0,'stage-container\n','')
            if args[:2]==['docker','cp']:shutil.copytree(staged,Path(args[-1]))
            return CompletedProcess(args,0,'','')
        with patch.object(install,'run_command',side_effect=command) as docker,patch.object(install.subprocess,'run') as system,patch.dict(os.environ,{'OMA_TV_IMAGE':'foreign:version','APP_VERSION':'foreign'}):
            install.install_project(self.root,self.home,image=image)
        env=install.read_env(self.root/'.env')
        self.assertEqual(env['OMA_TV_IMAGE'],image);self.assertEqual(env['APP_VERSION'],'v1.0.0')
        self.assertIn('# selected image version',(self.root/'.runtime/current/agent.py').read_text())
        self.assertIn(['docker','pull',image],[call.args[0] for call in docker.call_args_list])
        self.assertEqual(system.call_args_list[0].args[0],['docker','compose','up','-d','--wait','--wait-timeout','120','--no-build'])
        self.assertNotIn('--build',system.call_args_list[0].args[0])
        self.assertNotIn('OMA_TV_IMAGE',system.call_args_list[0].kwargs['env'])
        self.assertNotIn('APP_VERSION',system.call_args_list[0].kwargs['env'])
    def test_installer_does_not_replace_an_existing_image_version(self):
        one='ghcr.io/example/kamerablick:v1.0.0';two='ghcr.io/example/kamerablick:v2.0.0'
        install.prepare(self.root,self.home,image=one)
        before=(self.root/'.env').read_bytes()
        with self.assertRaisesRegex(ValueError,'Versionswechsel'):
            install.prepare(self.root,self.home,image=two)
        self.assertEqual(before,(self.root/'.env').read_bytes())
        install.prepare(self.root,self.home,image=one)
        self.assertEqual(before,(self.root/'.env').read_bytes())
    def test_preflight_accepts_pi2_armv7_and_rejects_armv6(self):
        with patch.object(install.platform,'machine',return_value='armv7l'),patch.object(install.shutil,'which',return_value=None):
            architecture=next(c for c in install.preflight(self.root) if c['name']=='Prozessorarchitektur')
            self.assertTrue(architecture['ok'])
        with patch.object(install.platform,'machine',return_value='armv6l'),patch.object(install.shutil,'which',return_value=None):
            architecture=next(c for c in install.preflight(self.root) if c['name']=='Prozessorarchitektur')
            self.assertFalse(architecture['ok'])
    def test_registry_image_must_use_an_explicit_version(self):
        self.assertEqual(install.registry_image('ghcr.io/example/kamerablick:v1.0.0'),'ghcr.io/example/kamerablick:v1.0.0')
        for value in ('ghcr.io/example/kamerablick:latest','python:3.13','ghcr.io/example/kamerablick','ghcr.io/example/kamerablick:v1;touch x'):
            with self.assertRaises(ValueError):install.registry_image(value)

if __name__ == '__main__': unittest.main()
