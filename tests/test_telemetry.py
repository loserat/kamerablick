import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock
sys.path.insert(0,str(Path(__file__).parents[1]/'app'))
from telemetry import Telemetry
from protect import ProtectError

class Clock:
    def __init__(self):self.now=1793380000.0
    def __call__(self):return self.now

class CameraTelemetry(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)/'telemetry.json'
        self.clock=Clock();self.config={'camera_source':'protect','camera_id':'camera-1'}
        self.credentials={'host':'https://192.0.2.1','api_key':'secret-key'}
        self.client=Mock();self.client.camera.return_value={'id':'camera-1','state':'CONNECTED','type':'G6','featureFlags':{'smartDetectTypes':['person','vehicle']}}
        self.monitor=self.new();self.spec=self.monitor.spec();self.monitor.select(self.spec);self.monitor.poll(self.spec);self.monitor.connected(self.spec)
    def new(self):return Telemetry(self.path,lambda:self.config,lambda:self.credentials,wall=self.clock,mono=self.clock,client_factory=lambda _:self.client)
    def tearDown(self):self.monitor.close();self.temp.cleanup()
    def motion(self,**changes):
        item={'modelKey':'event','id':'motion-1','device':'camera-1','type':'motion','start':self.clock.now*1000-1000}
        item.update(changes)
        return {'type':'add','item':item}
    def test_live_event_persists_without_raw_credentials(self):
        self.assertIsNone(self.monitor.snapshot()['motion_active'])
        self.monitor.event(self.spec,self.motion())
        status=self.monitor.snapshot()
        self.assertTrue(status['camera_fresh']);self.assertTrue(status['events_fresh']);self.assertTrue(status['motion_active'])
        self.assertIsNotNone(status['last_motion'])
        self.assertEqual(self.path.stat().st_mode&0o777,0o600)
        self.assertNotIn('secret-key',self.path.read_text());self.assertNotIn('192.0.2.1',self.path.read_text())
    def test_restart_preserves_history_but_never_old_connection_state(self):
        self.monitor.event(self.spec,self.motion());saved=self.monitor.snapshot()['last_motion']
        restarted=self.new();status=restarted.snapshot()
        self.assertEqual(status['last_motion'],saved)
        self.assertFalse(status['camera_fresh']);self.assertFalse(status['events_fresh']);self.assertIsNone(status['motion_active'])
    def test_failed_poll_and_connection_mark_current_values_unknown(self):
        self.monitor.event(self.spec,self.motion())
        self.client.camera.side_effect=ProtectError('Verbindung fehlgeschlagen')
        self.monitor.poll(self.spec)
        status=self.monitor.snapshot();self.assertFalse(status['camera_fresh']);self.assertIsNone(status['motion_active'])
        self.monitor.disconnected(self.spec,ConnectionError())
        status=self.monitor.snapshot();self.assertFalse(status['events_fresh']);self.assertIsNotNone(status['last_motion'])
    def test_expired_checks_cannot_stay_online(self):
        self.monitor.event(self.spec,self.motion());self.clock.now+=46
        status=self.monitor.snapshot();self.assertFalse(status['events_fresh']);self.assertFalse(status['camera_fresh']);self.assertIsNone(status['motion_active'])
    def test_history_is_separated_by_camera_and_console(self):
        self.monitor.event(self.spec,self.motion())
        self.config['camera_id']='camera-2';self.assertIsNone(self.monitor.snapshot()['last_motion'])
        self.config['camera_id']='camera-1';self.assertIsNotNone(self.monitor.snapshot()['last_motion'])
        self.credentials['host']='https://192.0.2.2';self.assertIsNone(self.monitor.snapshot()['last_motion'])
    def test_old_reply_after_selection_change_is_discarded(self):
        self.config['camera_id']='camera-2';self.monitor.snapshot()
        self.monitor.event(self.spec,self.motion());self.monitor.poll(self.spec)
        status=self.monitor.snapshot();self.assertIsNone(status['last_motion']);self.assertFalse(status['camera_fresh'])
    def test_rotation_keeps_history_but_restarts_connection(self):
        self.monitor.event(self.spec,self.motion());self.credentials['api_key']='rotated'
        status=self.monitor.snapshot();self.assertIsNotNone(status['last_motion']);self.assertFalse(status['events_fresh'])
        self.monitor.event(self.spec,self.motion(id='old-key-event',start=self.clock.now*1000))
        self.assertNotEqual(status['last_motion']['occurred_at'],__import__('telemetry').iso(self.clock.now))
    def test_invalid_other_camera_and_future_events_are_ignored(self):
        for changes in ({'device':'other'},{'modelKey':'camera'},{'start':self.clock.now},{'start':True},{'start':(self.clock.now+400)*1000},{'end':self.clock.now*1000-2000}):
            self.monitor.event(self.spec,self.motion(**changes))
        self.assertIsNone(self.monitor.snapshot()['last_motion']);self.assertFalse(self.path.exists())
    def test_duplicate_and_out_of_order_events_do_not_regress_history(self):
        newer=self.motion(start=self.clock.now*1000)
        self.monitor.event(self.spec,newer);saved=self.path.read_bytes()
        self.monitor.event(self.spec,newer);self.monitor.event(self.spec,self.motion(id='old',start=self.clock.now*1000-5000))
        self.assertEqual(saved,self.path.read_bytes())
    def test_overlapping_motion_end_does_not_clear_new_motion(self):
        self.monitor.event(self.spec,self.motion(id='m1'))
        self.monitor.event(self.spec,self.motion(id='m2',start=self.clock.now*1000))
        self.monitor.event(self.spec,self.motion(id='m1',end=self.clock.now*1000))
        self.assertTrue(self.monitor.snapshot()['motion_active'])
        self.monitor.event(self.spec,self.motion(id='m2',start=self.clock.now*1000,end=self.clock.now*1000))
        self.assertFalse(self.monitor.snapshot()['motion_active'])
    def test_duplicate_start_cannot_reopen_an_ended_motion(self):
        message=self.motion();self.monitor.event(self.spec,message)
        self.monitor.event(self.spec,self.motion(end=self.clock.now*1000))
        self.monitor.event(self.spec,message)
        self.assertFalse(self.monitor.snapshot()['motion_active'])
    def test_motion_without_end_is_not_claimed_current_forever(self):
        self.monitor.event(self.spec,self.motion());self.clock.now+=121
        self.monitor.poll(self.spec);self.monitor.touch(self.spec)
        self.assertIsNone(self.monitor.snapshot()['motion_active'])
    def test_smart_person_and_vehicle_are_explicit_separate_events(self):
        self.monitor.event(self.spec,self.motion(type='smartDetectZone',smartDetectTypes=['person','vehicle']))
        status=self.monitor.snapshot();self.assertIsNotNone(status['last_person']);self.assertIsNotNone(status['last_vehicle']);self.assertIsNone(status['last_motion'])
    def test_corrupt_storage_is_preserved_for_recovery(self):
        self.path.write_text('broken!');restarted=self.new();spec=restarted.spec();restarted.select(spec)
        restarted.event(spec,self.motion());self.assertEqual(self.path.read_text(),'broken!')
        self.assertIn('Ereignisdatei',restarted.snapshot()['last_error'])
    def test_unexpected_history_entry_does_not_break_status(self):
        self.path.write_text(json.dumps({'schema':1,'cameras':{self.spec['identity']:[]}}))
        self.assertIsNone(self.new().snapshot()['last_motion'])
    def test_corrupt_credentials_disable_monitor_without_claiming_old_data(self):
        self.credentials=['invalid configuration']
        status=self.monitor.snapshot()
        self.assertFalse(status['enabled']);self.assertFalse(status['events_fresh'])
        self.assertEqual(status['reason'],'configuration_error')
    def test_unavailable_and_manual_sources_never_create_fake_events(self):
        self.config={'camera_source':'demo','camera_id':'sample'}
        status=self.monitor.snapshot();self.assertFalse(status['enabled']);self.assertEqual(status['reason'],'demo');self.assertIsNone(status['last_motion'])
        self.config={'camera_source':'manual','stream_url':'rtsps://host/stream'}
        self.assertEqual(self.monitor.snapshot()['reason'],'manual')
    def test_unsupported_and_revoked_event_api_remain_distinguishable(self):
        for code,state in ((404,'unsupported'),(401,'auth_error'),(409,'certificate_error')):
            self.monitor.disconnected(self.spec,ProtectError('Nicht verfügbar',code))
            status=self.monitor.snapshot();self.assertEqual(status['events_state'],state);self.assertFalse(status['events_fresh'])

if __name__=='__main__':unittest.main()
