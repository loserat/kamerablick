import fcntl
import http.client
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import secrets
import shutil
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

PI=Path(__file__).parents[1]/'pi'
sys.path.insert(0,str(PI))
import install
import maintenance
import release_info
import update
import update_job
import activate_browser_updates


class BrowserMaintenance(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)/'project';self.home=Path(self.temp.name)/'home'
        (self.root/'pi').mkdir(parents=True)
        for name in install.RUNTIME_FILES:shutil.copy(PI/name,self.root/'pi'/name)
        install.prepare(self.root,self.home)
        env=self.root/'.env';env.write_text(env.read_text()+'APP_VERSION=v1.0.0\n')
        self.scheduled=[]
        self.manager=maintenance.Maintenance(self.root,scheduler=lambda *args,**kwargs:self.scheduled.append((args,kwargs)),persistent=lambda:True,active=lambda unit:False)
        self.release_patch=patch.object(release_info,'release',return_value={'version':'v1.0.1'});self.fetch=self.release_patch.start()
    def tearDown(self):self.release_patch.stop();self.temp.cleanup()
    def start(self):return self.manager.start('v1.0.1')

    def test_job_is_detached_and_only_read_only_watch_capability_is_returned(self):
        started=self.start();job=started['job'];private=self.manager.store.read()
        self.assertEqual(job['phase'],'queued');self.assertTrue(job['busy'])
        self.assertNotIn('watch_hash',job);self.assertNotIn('unit',job)
        self.assertNotIn(started['watch'],self.manager.store.path.read_text())
        self.assertEqual(self.manager.watch(started['watch'])['job']['id'],job['id'])
        self.assertEqual(self.manager.store.path.stat().st_mode&0o777,0o600)
        self.assertEqual(self.manager.store.directory.stat().st_mode&0o777,0o700)
        self.assertEqual(len(self.scheduled),1)
        self.assertTrue(private['unit'].startswith('kamerablick-update-'))

    def test_parallel_jobs_unknown_versions_and_downgrades_are_rejected(self):
        for tag in ('v0.9.9','v1.0.0','latest','v1.0.1;touch /tmp/x','ghcr.io/other/image:v1.0.1','v1.0.1-beta'):
            with self.assertRaises(ValueError):self.manager.start(tag)
        self.assertEqual(self.scheduled,[])
        self.start()
        with self.assertRaisesRegex(ValueError,'läuft bereits'):self.start()
        self.assertEqual(len(self.scheduled),1)

    def test_cli_lock_and_nonpersistent_user_prevent_start(self):
        self.manager.persistent=lambda:False
        with self.assertRaises(ValueError):self.start()
        self.manager.persistent=lambda:True
        with open(self.root/'.update.lock','a') as handle:
            fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
            with self.assertRaisesRegex(ValueError,'bereits ein Update'):self.start()
        self.assertEqual(self.scheduled,[])

    def test_failed_scheduler_never_leaves_a_permanent_running_job(self):
        self.manager.scheduler=lambda *a,**k:(_ for _ in ()).throw(OSError('test-only failure'))
        with self.assertRaises(ValueError):self.start()
        self.assertEqual(self.manager.store.public()['phase'],'failed')

    def test_wrong_and_expired_watch_tokens_are_rejected(self):
        result=self.start()
        for token in (None,'short','x'*43):
            with self.assertRaises(PermissionError):self.manager.watch(token)
        job=self.manager.store.read();job['created_at']-=25*3600;self.manager.store.write(job)
        with self.assertRaises(PermissionError):self.manager.watch(result['watch'])

    def test_reconciliation_ignores_active_worker_and_recovers_after_interrupt(self):
        self.start();self.scheduled.clear()
        state=self.root/'backups/update-state.json';state.parent.mkdir(exist_ok=True);state.write_text(json.dumps({'phase':'applying'}))
        with open(self.root/'.update.lock','a') as handle:
            fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB);self.manager.reconcile()
        self.assertEqual(self.scheduled,[])
        self.manager.reconcile()
        self.assertEqual(self.manager.store.public()['phase'],'recovering')
        self.assertTrue(self.scheduled[0][1]['recover'])

    def test_reconciliation_marks_an_abandoned_download_failed(self):
        self.start();self.manager.reconcile()
        self.assertEqual(self.manager.store.public()['phase'],'failed')
    def test_failed_recovery_is_not_repeated_on_every_status_poll(self):
        self.start();self.scheduled.clear()
        path=self.root/'backups/update-state.json';path.parent.mkdir(exist_ok=True);path.write_text(json.dumps({'phase':'rollback_failed'}))
        self.manager.reconcile();self.manager.store.phase('recovery_failed')
        self.manager.reconcile();self.manager.reconcile()
        self.assertEqual(len(self.scheduled),1)
        path.write_text(json.dumps({'phase':'rolled_back'}));self.manager.reconcile()
        self.assertEqual(self.manager.store.public()['phase'],'rolled_back')

    def test_worker_uses_only_the_fixed_image_and_reports_success(self):
        self.start();job=self.manager.store.read()
        with patch.object(update,'recover'),patch.object(update,'update') as apply:
            self.assertTrue(update_job.execute(self.root,job['id']))
        self.assertEqual(apply.call_args.args[0],'ghcr.io/loserat/kamerablick:v1.0.1')
        self.assertEqual(self.manager.store.public()['phase'],'complete')

    def test_worker_reports_rollback_and_never_returns_raw_error_text(self):
        self.start();job=self.manager.store.read()
        def fail(image,progress,verify):
            progress('rolling_back')
            path=self.root/'backups/update-state.json';path.parent.mkdir(exist_ok=True);path.write_text(json.dumps({'phase':'rolled_back'}))
            raise RuntimeError('private-error-with-password')
        with patch.object(update,'recover'),patch.object(update,'update',side_effect=fail):
            self.assertFalse(update_job.execute(self.root,job['id']))
        self.assertEqual(self.manager.store.public()['phase'],'rolled_back')
        self.assertNotIn('private-error',json.dumps(self.manager.store.public()))

    def test_prior_rollback_is_not_claimed_as_a_new_rollback(self):
        self.start();job=self.manager.store.read()
        path=self.root/'backups/update-state.json';path.parent.mkdir(exist_ok=True);path.write_text(json.dumps({'phase':'rolled_back'}))
        with patch.object(update,'recover'),patch.object(update,'update',side_effect=OSError('network unavailable')):
            self.assertFalse(update_job.execute(self.root,job['id']))
        self.assertEqual(self.manager.store.public()['phase'],'failed')

    def test_command_is_an_argument_list_without_shell_or_user_supplied_command(self):
        self.start();job=self.manager.store.read()
        with patch.object(maintenance.subprocess,'run') as run:self.manager.schedule(job)
        args=run.call_args.args[0]
        self.assertEqual(args[0],'systemd-run');self.assertIn('--user',args)
        self.assertIn('--property=Type=exec',args)
        self.assertNotIn('shell',run.call_args.kwargs)
        self.assertEqual(args[-1],job['id'])
        self.assertTrue(any(str(arg).endswith('/update_job.py') for arg in args))
    def test_wrong_image_provenance_is_rejected_and_staging_container_removed(self):
        from subprocess import CompletedProcess
        calls=[]
        def command(args,**kwargs):
            calls.append(args)
            output='stage\n' if args[:2]==['docker','create'] else json.dumps({'org.opencontainers.image.source':'https://github.com/other/project'})
            return CompletedProcess(args,0,output,'')
        with patch.object(update,'run',side_effect=command):
            with self.assertRaises(ValueError):update_job.verify_image('ghcr.io/loserat/kamerablick:v1.0.1')
        self.assertEqual(calls[-1],['docker','rm','stage'])
    def test_one_time_activation_keeps_existing_configuration_and_uses_updater(self):
        image='ghcr.io/loserat/kamerablick:v1.0.1'
        before=(self.root/'.env').read_bytes()
        with patch.object(maintenance,'persistent_user',return_value=True),patch.object(install,'preflight',return_value=[{'ok':True}]),patch.object(activate_browser_updates.subprocess,'run') as command,patch.object(install,'install_project') as installer:
            activate_browser_updates.activate(self.root,self.home,image)
        self.assertEqual(command.call_args.args[0][-1],image)
        installer.assert_called_once_with(self.root,self.home,image=image)
        self.assertEqual((self.root/'.env').read_bytes(),before)
    def test_one_time_activation_requires_persistent_host_service_first(self):
        with patch.object(maintenance,'persistent_user',return_value=False),patch.object(install,'install_project') as installer:
            with self.assertRaisesRegex(ValueError,'enable-linger'):
                activate_browser_updates.activate(self.root,self.home,'ghcr.io/loserat/kamerablick:v1.0.1')
            installer.assert_not_called()

    def test_bridge_http_requires_private_host_token_and_watch_capability(self):
        token='host-test-'+secrets.token_hex(20)
        httpd=ThreadingHTTPServer(('127.0.0.1',0),maintenance.handler(self.manager,token))
        thread=threading.Thread(target=httpd.serve_forever,daemon=True);thread.start()
        def request(path,body=None,credential=None):
            connection=http.client.HTTPConnection('127.0.0.1',httpd.server_port,timeout=4)
            headers={'Content-Type':'application/json'}
            if credential:headers['Authorization']='Bearer '+credential
            connection.request('POST' if body is not None else 'GET',path,body=json.dumps(body) if body is not None else None,headers=headers)
            response=connection.getresponse();raw=json.loads(response.read());status=response.status;connection.close();return status,raw
        try:
            self.assertEqual(request('/healthz')[0],401)
            with patch.object(self.manager,'reconcile') as reconcile:
                code,health=request('/healthz',credential=token)
                self.assertEqual(code,200)
                self.assertEqual(health['protocol'],1)
                self.assertTrue(health['available'])
                self.assertNotIn('job',health)
                reconcile.assert_not_called()
            self.assertEqual(request('/status')[0],401)
            self.assertEqual(request('/update',{'version':'v1.0.1'})[0],401)
            code,data=request('/update',{'version':'v1.0.1'},token)
            self.assertEqual(code,202)
            self.assertEqual(request('/watch',{'watch':'wrong'},token)[0],401)
            code,result=request('/watch',{'watch':data['watch']},token)
            self.assertEqual(code,200);self.assertNotIn('watch_hash',json.dumps(result))
        finally:httpd.shutdown();httpd.server_close()


class ReleaseSource(unittest.TestCase):
    def setUp(self):release_info._cache.clear()
    def test_semantic_versions_and_monotonic_updates(self):
        self.assertTrue(release_info.newer('v0.10.0','v0.9.9'))
        self.assertFalse(release_info.newer('v1.0.0','v1.0.0'))
        for tag in ('v1.0.0-beta','v01.0.0','latest','v1.0.0/../../x'):
            with self.assertRaises(ValueError):release_info.version(tag)
    def test_only_official_stable_releases_are_returned_and_redirects_refused(self):
        from unittest.mock import MagicMock
        response=MagicMock();response.status=200
        response.read.return_value=json.dumps({'tag_name':'v1.2.3','body':'notes','draft':False,'prerelease':False}).encode()
        connection=MagicMock();connection.getresponse.return_value=response
        with patch.object(release_info.http.client,'HTTPSConnection',return_value=connection) as transport:
            result=release_info.release('v1.2.3')
            self.assertEqual(result['url'],'https://github.com/loserat/kamerablick/releases/tag/v1.2.3')
            self.assertEqual(transport.call_args.args[0],'api.github.com')
            self.assertEqual(connection.request.call_args.args[1],'/repos/loserat/kamerablick/releases/tags/v1.2.3')
            response.status=302
            with self.assertRaises(ValueError):release_info.release(refresh=True)
            response.status=200;response.read.return_value=json.dumps({'tag_name':'v1.2.3','prerelease':True}).encode()
            with self.assertRaises(ValueError):release_info.release(refresh=True)
