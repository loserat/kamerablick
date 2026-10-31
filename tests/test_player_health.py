import json
from pathlib import Path
import socket
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parents[1]/'pi'))
from player_health import PlayerHealth, read_progress
from agent import Controller


class Progress(unittest.TestCase):
    def setUp(self):
        self.now=0
        self.value=0.0
        self.health=PlayerHealth(lambda:self.now,lambda path:self.value)
        self.health.begin('/private/test.sock')

    def sample(self,at,value):
        self.now,self.value=at,value
        self.health.sample()
        return self.health.snapshot()

    def test_process_or_single_frame_is_not_progress(self):
        self.assertFalse(self.sample(0,0)['progress_fresh'])
        self.assertFalse(self.sample(10,0)['progress_fresh'])
        self.assertFalse(self.sample(29,0)['restart_due'])
        self.assertTrue(self.sample(30,0)['restart_due'])

    def test_progress_stall_and_backward_timestamp_recovery(self):
        self.sample(0,0)
        self.assertTrue(self.sample(1,1)['progress_fresh'])
        self.assertFalse(self.sample(7,1)['progress_fresh'])
        self.assertFalse(self.sample(20,1)['restart_due'])
        self.assertTrue(self.sample(21,1)['restart_due'])
        self.assertTrue(self.sample(22,.1)['progress_fresh'])

    def test_ipc_failure_and_delayed_sampling_are_not_fresh(self):
        self.sample(0,0);self.sample(1,1)
        self.health.reader=MagicMock(side_effect=TimeoutError())
        self.now=2;self.health.sample()
        self.assertFalse(self.health.snapshot()['progress_fresh'])
        self.assertFalse(self.health.snapshot()['restart_due'])
        self.health.reader=lambda path:2
        self.now=3;self.health.sample()
        self.assertTrue(self.health.snapshot()['progress_fresh'])
        self.now=7
        self.assertFalse(self.health.snapshot()['progress_fresh'])

    def test_only_continuous_progress_resets_failure_backoff(self):
        self.sample(0,0)
        for second in range(1,12): self.sample(second,second)
        self.assertTrue(self.health.snapshot()['stable'])
        self.assertFalse(self.sample(16,16)['stable'])
        self.health.clear()
        self.assertEqual(self.health.snapshot()['state'],'stopped')
        self.assertFalse(self.health.snapshot()['restart_due'])

    def test_stalled_controller_retries_without_changing_tv_or_deadline(self):
        with tempfile.TemporaryDirectory() as temp:
            c=Controller(Path(temp)/'config.json',clock=lambda:self.now)
            c.settings.update(stream_url='rtsps://test/secret',auto_off_minutes=2)
            c.want_on=True;c.deadline=120
            player=MagicMock();player.poll.return_value=None;c.player=player
            c.health=self.health
            self.sample(0,0);self.sample(1,1);self.now=21
            with patch.object(c,'cec') as cec,patch.object(c,'start_player') as start:
                c.tick()
                self.assertIsNone(c.player);self.assertEqual(c.retry_at,26)
                self.assertEqual(c.deadline,120)
                self.now=25;c.tick();start.assert_not_called()
                self.now=26;c.tick();start.assert_called_once()
                cec.assert_not_called()
            player.terminate.assert_called_once()

    def test_deadline_and_back_take_precedence_over_a_frozen_player(self):
        with tempfile.TemporaryDirectory() as temp:
            c=Controller(Path(temp)/'config.json',clock=lambda:self.now)
            c.want_on=True;c.deadline=20
            c.player=MagicMock();c.player.poll.return_value=None
            c.health=self.health;self.now=30
            with patch.object(c,'cec') as cec,patch.object(c,'start_player') as start:
                c.tick();cec.assert_called_once_with('standby 0\n');start.assert_not_called()
                self.assertFalse(c.want_on)
            c.want_on=True;c.deadline=0;c.player=MagicMock();c.player.poll.return_value=42
            c.tick();self.assertFalse(c.want_on)
            self.assertEqual(c.health.snapshot()['state'],'stopped')

    def test_player_launch_failure_keeps_toggle_off_available(self):
        with tempfile.TemporaryDirectory() as temp:
            c=Controller(Path(temp)/'config.json',clock=lambda:self.now)
            c.settings.update(stream_url='rtsps://test/secret')
            with patch.object(c,'cec') as cec,patch.object(c,'start_player',side_effect=OSError()):
                c.action('on');self.assertTrue(c.want_on);self.assertEqual(c.retry_at,5)
                c.action('toggle');self.assertFalse(c.want_on)
                self.assertEqual(cec.call_args.args[0],'standby 0\n')
    def test_exited_process_cannot_retain_a_fresh_progress_status(self):
        with tempfile.TemporaryDirectory() as temp:
            c=Controller(Path(temp)/'config.json',clock=lambda:self.now)
            c.health=self.health;c.want_on=True
            c.player=MagicMock();c.player.poll.return_value=None
            self.sample(0,0);self.sample(1,1)
            self.assertTrue(c.status()['player_health']['progress_fresh'])
            c.player.poll.return_value=1
            state=c.status()
            self.assertFalse(state['player_running'])
            self.assertFalse(state['player_health']['progress_fresh'])
            self.assertEqual(state['player_health']['state'],'reconnecting')
            # Reading status does not erase the previous progress observation.
            self.assertTrue(c.health.snapshot()['progress_fresh'])
    def test_stable_playback_clears_old_retry_delay_before_next_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            c=Controller(Path(temp)/'config.json',clock=lambda:self.now)
            c.health=self.health;c.want_on=True;c.retries=4;c.retry_at=60
            c.player=MagicMock();c.player.poll.return_value=None
            self.sample(0,0)
            for second in range(1,12): self.sample(second,second)
            c.tick()
            c.player.poll.return_value=1;self.now=12
            with patch.object(c,'start_player') as start:
                c.tick();start.assert_called_once()
            self.assertEqual(c.retries,1)


class Ipc(unittest.TestCase):
    def exchange(self,replies,callback):
        # Short path also fits macOS's Unix-socket limit.
        with tempfile.TemporaryDirectory(dir='/tmp') as temp:
            path=Path(temp)/'mpv.sock'
            listener=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
            listener.bind(str(path));listener.listen(1)
            received=[]
            def serve():
                try:
                    conn,_=listener.accept()
                    with conn:
                        conn.settimeout(1)
                        pending=b''
                        while pending.count(b'\n')<2: pending+=conn.recv(4096)
                        received.extend(json.loads(line) for line in pending.splitlines())
                        for chunk in replies:
                            if chunk is None: time.sleep(.4)
                            else: conn.sendall(chunk)
                except (OSError,TimeoutError): pass
            thread=threading.Thread(target=serve);thread.start()
            try: callback(path,received)
            finally: thread.join(timeout=2);listener.close()
            self.assertFalse(thread.is_alive())

    def test_fragmented_reordered_responses_and_events(self):
        replies=[b'{"event":"file-loaded"}\n{"request_id":2,"error":"success","data":{"w":640,"h":360}}\n',
                 b'{"request_id":1,"error":"success","da',b'ta":12.25}\n']
        def check(path,received):
            self.assertEqual(read_progress(path),12.25)
            self.assertEqual([r['command'][0] for r in received],['get_property','get_property'])
        self.exchange(replies,check)

    def test_audio_only_unavailable_and_invalid_position_are_rejected(self):
        for pos,video in ((1,None),(True,{'w':640,'h':360}),('nan',{'w':640,'h':360})):
            replies=[(json.dumps({'request_id':key,'error':'success','data':data})+'\n').encode()
                     for key,data in ((1,pos),(2,video))]
            def check(path,received):
                with self.assertRaises(ValueError): read_progress(path)
            self.exchange(replies,check)

    def test_ipc_timeout_and_oversized_input_are_bounded(self):
        def timeout(path,received):
            before=time.monotonic()
            with self.assertRaises(TimeoutError): read_progress(path,timeout=.08)
            self.assertLess(time.monotonic()-before,.3)
        self.exchange([None],timeout)
        def oversized(path,received):
            with self.assertRaises(ValueError): read_progress(path)
        self.exchange([b' ' * 70000],oversized)


if __name__=='__main__': unittest.main()
