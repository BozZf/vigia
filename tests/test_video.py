import json
import re
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import video


class PreviewTests(unittest.TestCase):
    def test_crash_retains_stages_without_private_callback(self):
        events = [{'stage':'video_window_ready','code':0},
                  {'stage':'light_payload','hex':'PRIVATE'},
                  {'stage':'video_player_created','code':0,'id':'PRIVATE'}]
        script = 'import sys;print('+repr('\n'.join(map(json.dumps,events)))+');sys.exit(62)'
        with tempfile.TemporaryDirectory() as tmp, patch.object(video.core,'ROOT',Path(tmp)):
            with subprocess.Popen([sys.executable,'-c',script],stdout=subprocess.PIPE) as proc:
                report = {'events':[],'live_image_observed':'unknown'}
                self.assertEqual(video.collect(proc,report),62)
            saved=(Path(tmp)/'resultado_video_yoosee.json').read_text()
            self.assertNotIn('PRIVATE',saved)
            self.assertEqual([e['stage'] for e in report['events']],['video_window_ready','video_player_created'])
            self.assertEqual(report['live_image_observed'],'unknown')

    def test_audio_records_each_attempted_direction_separately(self):
        report = {'events':[{'stage':'audio_listen','code':1},{'stage':'talk_requested','code':0}]}
        with patch('builtins.input',side_effect=['s','n']), patch.object(video,'save'):
            self.assertTrue(video.audio_observations(report))
        self.assertEqual(report['audio_observed'],{'camera_to_pc':'yes','pc_to_camera':'no'})

    def test_unattempted_audio_does_not_prompt(self):
        report = {'events':[{'stage':'video_play_return','code':0}]}
        with patch('builtins.input',side_effect=AssertionError):
            self.assertFalse(video.audio_observations(report))
        self.assertNotIn('audio_observed',report)

    def test_microphone_only_skips_listening_question(self):
        report = {'events':[{'stage':'talk_requested','code':0}]}
        with patch('builtins.input',return_value='') as ask, patch.object(video,'save'):
            self.assertTrue(video.audio_observations(report))
            ask.assert_called_once()
        self.assertEqual(report['audio_observed'],{'pc_to_camera':'unknown'})


    def test_player_hash_matches_native_audio_abi_guard(self):
        src = (video.core.ROOT/'src/adapter.cpp').read_text()
        values = re.search(r'const unsigned char player_hash\[\]=\{([^}]+)\}', src).group(1)
        self.assertEqual(bytes(int(v,16) for v in values.split(',')).hex(),video.PLAYER_HASH)
