"""Test coordinated update/recovery state, in addition to opt-in Docker acceptance."""
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch
from subprocess import CompletedProcess
sys.path.insert(0,str(Path(__file__).parents[1]/'pi'))
import update
import install

class UpdateFlow(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)/'project';self.home=Path(self.temp.name)/'home'
        (self.root/'pi').mkdir(parents=True)
        source=Path(__file__).parents[1]/'pi'
        for name in install.RUNTIME_FILES: shutil.copy(source/name,self.root/'pi'/name)
        install.prepare(self.root,self.home)
        self.old_runtime=(self.root/'.runtime/current').resolve()
        self.env=(self.root/'.env').read_text()
        self.calls=[];self.fail_start=False;self.extra_runtime=()
        self.root_patch=patch.object(update,'ROOT',self.root);self.root_patch.start()
        self.run_patch=patch.object(update,'run',side_effect=self.command);self.run_patch.start()
        self.health_patch=patch.object(update,'wait_healthy');self.health=self.health_patch.start()
    def tearDown(self):
        self.health_patch.stop();self.run_patch.stop();self.root_patch.stop();self.temp.cleanup()
    def command(self,args,**kwargs):
        self.calls.append((args,kwargs))
        output=''
        if args[:2]==['docker','create']:output='staging-container\n'
        elif args[:2]==['docker','cp']:
            dest=Path(args[-1]);dest.mkdir()
            for name in (*install.RUNTIME_FILES,*self.extra_runtime):
                (dest/name).write_text((self.root/'pi'/name).read_text()+'\n# updated\n')
        elif args[:3]==['docker','compose','ps']:output='running-container\n'
        elif args[:2]==['docker','inspect']:output='sha256:old-image\n'
        elif args[:3]==['docker','compose','exec'] and args[-1]==update.SNAPSHOT:
            output=json.dumps({'config.json':json.dumps({'gpio_pin':17}),'protect.json':json.dumps({'api_key':'test-secret'})})
        elif args[:4]==['systemctl','--user','is-active','--quiet']:
            return CompletedProcess(args,3,'','')
        elif args[:3]==['docker','compose','up'] and self.fail_start:
            self.fail_start=False
            raise RuntimeError('simulated new image failure')
        return CompletedProcess(args,0,output,'')
    def test_success_changes_container_and_runtime_with_private_backup(self):
        update.update('ghcr.io/example/oma-tv:v1.2.0')
        self.assertNotEqual((self.root/'.runtime/current').resolve(),self.old_runtime)
        self.assertIn('OMA_TV_IMAGE=ghcr.io/example/oma-tv:v1.2.0',(self.root/'.env').read_text())
        state=json.loads((self.root/'backups/update-state.json').read_text())
        self.assertEqual(state['phase'],'complete')
        backup=Path(state['backup'])/'data.json'
        self.assertIn('test-secret',backup.read_text());self.assertEqual(backup.stat().st_mode&0o777,0o600)
    def test_start_failure_persists_previous_image_and_runtime(self):
        self.fail_start=True
        with self.assertRaisesRegex(RuntimeError,'vorherige Version'): update.update('ghcr.io/example/oma-tv:v1.2.0')
        self.assertEqual((self.root/'.runtime/current').resolve(),self.old_runtime)
        env=(self.root/'.env').read_text()
        self.assertIn('OMA_TV_IMAGE=oma-tv-rollback:',env);self.assertNotIn('v1.2.0',env)
        self.assertEqual(json.loads((self.root/'backups/update-state.json').read_text())['phase'],'rolled_back')
        restore=[kwargs['input'] for args,kwargs in self.calls if args[:3]==['docker','compose','run']]
        self.assertIn('test-secret',restore[0])
    def test_failed_health_restores_previous_runtime(self):
        self.health.side_effect=[RuntimeError('bad health'),None]
        with self.assertRaises(RuntimeError): update.update('ghcr.io/example/oma-tv:v1.2.0')
        self.assertEqual((self.root/'.runtime/current').resolve(),self.old_runtime)
        self.assertEqual(self.health.call_count,2)
    def test_interrupted_update_recovers_on_next_start(self):
        update.update('ghcr.io/example/oma-tv:v1.2.0')
        state=json.loads((self.root/'backups/update-state.json').read_text());state['phase']='applying';update.write_state(state)
        update.recover()
        self.assertEqual((self.root/'.runtime/current').resolve(),self.old_runtime)
        self.assertEqual(json.loads((self.root/'backups/update-state.json').read_text())['phase'],'rolled_back')
    def test_recovery_removes_config_that_did_not_exist_before_update(self):
        update.update('ghcr.io/example/oma-tv:v1.2.0')
        manifest=json.loads((self.root/'.install.json').read_text())
        host=Path(manifest['agent_config']);host.parent.mkdir(parents=True,exist_ok=True);host.write_text('{"new_schema":true}')
        state=json.loads((self.root/'backups/update-state.json').read_text());state['phase']='applying';update.write_state(state)
        update.recover();self.assertFalse(host.exists())
    def test_no_unmanaged_update(self):
        (self.root/'.install.json').unlink()
        with self.assertRaisesRegex(RuntimeError,'Installation fehlt'):update.update('ghcr.io/example/oma-tv:v1.2.0')
        self.assertEqual(self.calls,[])
    def test_new_runtime_helper_is_taken_from_image(self):
        self.extra_runtime=('future_helper.py',)
        (self.root/'pi/future_helper.py').write_text('VALUE=42\n')
        update.update('ghcr.io/example/oma-tv:v2.0.0')
        self.assertIn('VALUE=42',(self.root/'.runtime/current/future_helper.py').read_text())

if __name__=='__main__':unittest.main()
