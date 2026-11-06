import sys
import tempfile
import unittest
import subprocess
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parents[1] / 'pi'))
from cec_bridge import CecBridge, RemoteInput, connected_adapter
from agent import Controller


class CecInput(unittest.TestCase):
    def setUp(self):
        self.now = 100
        self.remote = RemoteInput(lambda: self.now)
        self.client = 'a' * 24

    def poll(self, previous=None, client=None):
        return self.remote.poll({'client': client or self.client,
                                 'boot': previous['boot'] if previous else None,
                                 'cursor': previous['cursor'] if previous else None})

    def test_hold_release_unknown_key_and_diagnostics(self):
        for _ in range(4): self.remote.callback(0, 0)
        self.remote.callback(0, 800)
        self.remote.callback(0, 0)
        self.assertEqual(self.remote.take(), ['Enter', 'Enter'])
        self.remote.callback(0x41, 0)  # Volume is never a TV-menu action.
        self.assertEqual(self.remote.take(), [])
        self.assertFalse(self.remote.diagnostic()['last_key']['supported'])

    def test_first_poll_and_duplicate_poll_never_replay_keys(self):
        self.remote.publish('Enter')
        baseline = self.poll()
        self.assertEqual(baseline['events'], [])
        self.remote.publish('ArrowRight')
        response = self.poll(baseline)
        self.assertEqual(response['events'], [{'id': 2, 'key': 'ArrowRight'}])
        self.assertEqual(self.poll(response)['events'], [])

    def test_stale_input_is_discarded_before_and_after_routing(self):
        self.remote.callback(0, 0)
        baseline = self.poll()
        self.remote.publish('Enter')
        self.now += 2
        self.assertEqual(self.remote.take(), [])
        self.assertEqual(self.poll(baseline)['events'], [])

    def test_second_browser_cannot_duplicate_an_action(self):
        first = self.poll()
        self.remote.publish('Enter')
        second = self.poll(client='b' * 24)
        self.assertTrue(second['waiting'])
        self.assertEqual(second['events'], [])
        self.assertEqual(len(self.poll(first)['events']), 1)
        self.now += 3
        self.assertEqual(self.poll(second, 'b' * 24)['events'], [])
        self.assertTrue(self.poll(first)['waiting'])

    def test_reconnect_resets_held_key_and_cursor(self):
        baseline = self.poll()
        self.remote.callback(0, 0)
        self.remote.publish('Enter')
        self.remote.reset()
        self.assertNotEqual(self.poll(baseline)['boot'], baseline['boot'])
        self.assertEqual(self.remote.take(), [])
        self.remote.callback(0, 0)
        self.assertEqual(self.remote.take(), ['Enter'])

    def test_bounded_queue_and_validation(self):
        baseline = self.poll()
        for _ in range(1000): self.remote.publish('Enter')
        self.assertEqual(len(self.poll(baseline)['events']), 32)
        for body in ({}, {'client': 'x'}, {'client': self.client, 'cursor': True},
                     {'client': self.client, 'cursor': -1}):
            with self.assertRaises(ValueError): self.remote.poll(body)

    def test_player_back_is_handled_without_a_browser_and_not_replayed(self):
        with tempfile.TemporaryDirectory() as temp:
            controller = Controller(Path(temp) / 'config.json')
            controller.want_on = True
            controller.player = MagicMock()
            controller.player.poll.return_value = None
            controller.remote.callback(0x0d, 0)
            controller.tick()
            self.assertFalse(controller.want_on)
            self.assertIsNone(controller.player)
            self.assertEqual(controller.remote.sequence, 0)
            controller.remote.callback(0x01, 0)
            controller.tick()
            self.assertEqual(controller.remote.sequence, 1)


class CecDriver(unittest.TestCase):
    def setUp(self):
        self.remote = RemoteInput()
        self.bridge = CecBridge(self.remote)
        self.process = MagicMock()
        self.process.poll.return_value = None
        self.bridge.process = self.process

    def opened(self, address=4):
        self.bridge.line(f'NOTICE: [123] logical address(es) = Playback 1 ({address})')
        self.bridge.line('NOTICE: [124] connection opened')

    def test_directed_tv_keys_only_and_no_tx_broadcast_or_other_players(self):
        self.opened()
        for frame in ('>> 08:44:00','>> 0f:44:00','>> 54:44:00','<< 04:44:00'):
            self.bridge.line('TRAFFIC: [125] '+frame)
        self.assertEqual(self.remote.take(), [])
        self.bridge.line('TRAFFIC: [126] >> 04:44:00')
        self.bridge.line('TRAFFIC: [127] >> 04:44:00')
        self.bridge.line('TRAFFIC: [128] >> 04:45')
        self.bridge.line('TRAFFIC: [129] >> 04:44:00')
        self.assertEqual(self.remote.take(), ['Enter', 'Enter'])
        self.assertTrue(self.bridge.snapshot()['connected'])

    def test_adapter_address_changes_and_missing_or_bad_frames(self):
        self.bridge.line('TRAFFIC: [1] >> 04:44:00')
        self.assertEqual(self.remote.take(), [])
        self.opened(8)
        for frame in ('>> 04:44:00','>> 08:44','>> 08:44:00:00','>> gg:44:00'):
            self.bridge.line('TRAFFIC: [2] '+frame)
        self.bridge.line('TRAFFIC: [3] >> 08:44:01')
        self.assertEqual(self.remote.take(), ['ArrowUp'])

    def test_lost_connection_clears_keys_and_prevents_commands(self):
        self.opened()
        self.bridge.line('TRAFFIC: [1] >> 04:44:00')
        self.bridge.line('Connection lost - trying to reconnect')
        self.assertFalse(self.bridge.snapshot()['connected'])

        self.assertEqual(self.remote.take(), [])
        with self.assertRaises(RuntimeError): self.bridge.command('on')
        self.opened()
        self.bridge.command('on');self.bridge.command('off')
        self.assertEqual([call.args[0] for call in self.process.stdin.write.call_args_list],
                         ['on 0\nas\n', 'standby 0\n'])
        self.bridge.line('ERROR: [1] command was not acked')
        self.assertIn('nicht bestätigt', self.bridge.message)
        self.process.poll.return_value = 1
        self.assertFalse(self.bridge.snapshot()['connected'])

class CecProcess(unittest.TestCase):
    def test_real_pipes_input_stream_and_service_shutdown(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'fake-cec-client.py'
            path.write_text("import sys\nprint('logical address(es) = Playback 1 (4)',flush=True)\nprint('connection opened',flush=True)\nfor line in sys.stdin:\n if line.strip()=='on 0':\n  print('TRAFFIC: [1] >> 04:44:00',flush=True)\n  print('TRAFFIC: [2] >> 04:45',flush=True)\n")
            calls=[]
            def factory(args,**kwargs):
                calls.append(args)
                return subprocess.Popen([sys.executable,'-u',str(path)],**kwargs)
            remote=RemoteInput();bridge=CecBridge(remote,factory,adapter_probe=lambda:'/dev/cec1')
            bridge.start()
            try:
                deadline=time.monotonic()+3
                while not bridge.snapshot()['connected'] and time.monotonic()<deadline: time.sleep(.02)
                self.assertTrue(bridge.snapshot()['connected'])
                self.assertNotIn('-s',calls[0])
                self.assertEqual(calls[0][-3:],['-aw','0','/dev/cec1'])
                self.assertEqual(bridge.snapshot()['adapter'],'/dev/cec1')
                bridge.command('on')
                keys=[]
                while not keys and time.monotonic()<deadline:
                    keys=remote.take();time.sleep(.02)
                self.assertEqual(keys,['Enter'])
            finally: bridge.close()
            self.assertFalse(bridge.thread.is_alive())
            self.assertIsNone(bridge.process)


class CecAdapters(unittest.TestCase):
    def test_second_connected_hdmi_and_unavailable_first_adapter(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            for name in ('cec0','cec1','cec1-untrusted'): (root/name).touch()
            def ioctl(handle, request, value, mutate):
                self.assertEqual(request,0x80026101)
                value[0]=0xffff if Path(handle.name).name=='cec0' else 0x4000
            with patch('cec_bridge.fcntl.ioctl',side_effect=ioctl):
                self.assertEqual(connected_adapter(root),str(root/'cec1'))
            def unavailable(handle, request, value, mutate):
                if Path(handle.name).name=='cec0': raise PermissionError()
                value[0]=0x4000
            with patch('cec_bridge.fcntl.ioctl',side_effect=unavailable):
                self.assertEqual(connected_adapter(root),str(root/'cec1'))

    def test_disconnected_or_unreadable_kernel_adapters_use_libcec_discovery(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'cec0').touch()
            with patch('cec_bridge.fcntl.ioctl'):
                self.assertIsNone(connected_adapter(root))
            with patch('cec_bridge.fcntl.ioctl',side_effect=OSError()):
                self.assertIsNone(connected_adapter(root))

    def test_hdmi_change_releases_old_helper_before_opening_new_one(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'helper.py'
            path.write_text("import time\nprint('connection opened',flush=True)\ntime.sleep(30)\n")
            selected=['/dev/cec0'];calls=[];processes=[]
            def factory(args,**kwargs):
                self.assertTrue(all(p.poll() is not None for p in processes))
                calls.append(args)
                process=subprocess.Popen([sys.executable,'-u',str(path)],**kwargs)
                processes.append(process)
                return process
            bridge=CecBridge(RemoteInput(),factory,adapter_probe=lambda:selected[0])
            bridge.start()
            try:
                deadline=time.monotonic()+3
                while not bridge.snapshot()['connected'] and time.monotonic()<deadline:time.sleep(.02)
                self.assertTrue(bridge.snapshot()['connected'])
                selected[0]='/dev/cec1'
                deadline=time.monotonic()+13
                while len(calls)<2 and time.monotonic()<deadline:time.sleep(.05)
                self.assertEqual([args[-1] for args in calls],['/dev/cec0','/dev/cec1'])
            finally:bridge.close()
            self.assertTrue(all(p.poll() is not None for p in processes))



if __name__ == '__main__': unittest.main()
