import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import iniciar as core
import luz
import sessao_luz


def wire(value):
    return json.dumps({'stage':'light_payload','hex':json.dumps(value).encode().hex()}).encode()+b'\n'


def result(value=None):
    return {'exit_code':0,'timed_out':False,'events':[],
            'light':core.summarize_light(wire(value) if value is not None else b'')}


class LightTests(unittest.TestCase):
    def test_explicit_response_codes(self):
        self.assertEqual(core.summarize_light(wire({'type':11,'errCode':0}))['command_response'],'accepted')
        self.assertEqual(core.summarize_light(wire({'errCode':0}))['command_response'],'accepted')
        out=core.summarize_light(wire({'type':11,'errCode':-2020}))
        self.assertEqual(out['command_response'],'rejected');self.assertEqual(out['response_code'],-2020)

    def test_light_reply_without_error_code(self):
        light = core.summarize_light(wire({'type': 11}))
        self.assertEqual(light['command_response'], 'received')
        self.assertNotIn('response_code', light)

    def test_missing_error_or_unrelated_reply_never_success(self):
        for value in ({},{'type':11,'errCode':None},{'code':0},{'stVal':1},{'type':12,'errCode':0},
                      {'type':True,'errCode':0},{'type':'11','errCode':0},
                      {'errCode':False},{'errCode':'0'},{'errCode':2**40},[],0,None):
            with self.subTest(value=value):
                self.assertEqual(core.summarize_light(wire(value))['command_response'],'unrecognized')

    def test_ack_and_property_data_do_not_confirm_light(self):
        raw=b'{"stage":"light_ack","code":0}\n'+wire({'errCode':0}).replace(b'light_payload',b'property_payload')
        self.assertFalse(core.summarize_light(raw)['payload_received'])
        self.assertEqual(core.summarize_light(raw)['command_response'],'not_received')

    def test_invalid_payload_and_nul_terminator(self):
        for encoded in ('xx','f','ab'*65537,'ff','7b'):
            out=core.summarize_light(json.dumps({'stage':'light_payload','hex':encoded}).encode())
            self.assertNotEqual(out['command_response'],'accepted')
        encoded=b'{"type":11,"errCode":0}\0'.hex()
        self.assertEqual(core.summarize_light(json.dumps({'stage':'light_payload','hex':encoded}).encode())['command_response'],'accepted')

    def test_response_and_events_do_not_disclose_unknown_fields(self):
        raw=wire({'type':11,'errCode':0,'secret-key':'TOKEN_SECRET','cameraId':'PRIVATE_CAMERA','ssid':'PRIVATE_WIFI'})
        output=json.dumps(core.summarize_light(raw))+json.dumps(core.parse_events(raw))
        for secret in ('TOKEN_SECRET','PRIVATE_CAMERA','PRIVATE_WIFI','secret-key','cameraId','ssid'):
            self.assertNotIn(secret,output)

    def test_worker_selects_only_requested_action_and_uses_stdin(self):
        class Worker:
            returncode=0
            def communicate(self,payload,timeout):
                self.payload=payload;return wire({'type':11,'errCode':0}),None
        for action in ('on','off'):
            worker=Worker()
            with patch.object(core.subprocess,'Popen',return_value=worker) as popen:
                out=core.native_test(Path('.'),('111','TOKEN_SECRET'),'222',action=action)
            self.assertEqual(popen.call_count,1)
            args=popen.call_args.args[0]
            self.assertEqual(args[-1],'--light-'+action)
            self.assertNotIn('TOKEN_SECRET',str(args))
            self.assertEqual(worker.payload,b'111\nTOKEN_SECRET\n222\n')
            self.assertEqual(out['light']['command_response'],'accepted')
            self.assertNotIn('property',out)

    def test_invalid_action_or_missing_session_never_starts_worker(self):
        with patch.object(core.subprocess,'Popen') as popen:
            for action,session,device in [('siren',('1','t'),'2'),('--read',('1','t'),'2'),('on',None,'2'),('off',('1','t'),None)]:
                with self.assertRaises(core.TestError):core.native_test(Path('.'),session,device,action)
            popen.assert_not_called()

    def test_timeout_kills_once_and_preserves_light_context(self):
        class Worker:
            calls=0
            killed=False
            def communicate(self,*args,**kwargs):
                self.calls+=1
                if self.calls==1:raise subprocess.TimeoutExpired('worker',65)
                return b'{"stage":"light_ack","code":0}\n',None
            def kill(self):self.killed=True
        worker=Worker()
        with patch.object(core.subprocess,'Popen',return_value=worker) as popen:
            out=core.native_test(Path('.'),('1','token'),'2','off')
        self.assertTrue(worker.killed);self.assertEqual(popen.call_count,1)
        self.assertTrue(out['timed_out']);self.assertEqual(out['action'],'off')
        self.assertEqual(out['light']['command_response'],'not_received')

    def test_observed_target_without_transition_is_not_complete(self):
        for before,after in [('on','on'),('unknown','on'),('off','unknown'),('off','off')]:
            self.assertFalse(luz.observation('on',before,after)['transition_observed'])
        self.assertTrue(luz.observation('on','off','on')['transition_observed'])
        self.assertTrue(luz.observation('off','on','off')['transition_observed'])

    def test_menu_exit_sends_nothing(self):
        channel = Mock()
        with patch('builtins.input', side_effect=['invalid', '0']), contextlib.redirect_stdout(io.StringIO()):
            luz.run_menu(channel, {'attempts': []})
        channel.send.assert_not_called()

    def test_both_commands_use_one_live_child_and_eof(self):
        # A stand-in process requires a single set of credentials, then ON and
        # OFF in order. A second registration or a premature EOF fails the test.
        script = """
import json, sys
assert [input(), input(), input()] == ['111', 'TEST_TOKEN', '222']
for action in ('on', 'off'):
    assert input() == action
    print(json.dumps({'stage':'light_payload','hex':b'{"type":11}'.hex()}), flush=True)
    print(json.dumps({'stage':'command_done','code':0}), flush=True)
assert sys.stdin.read() == ''
"""
        popen = subprocess.Popen
        children = []
        def launch(args, **kwargs):
            self.assertEqual(args[-1], '--light-menu')
            child = popen([sys.executable, '-u', '-c', script], **kwargs)
            children.append(child)
            return child
        report = {'attempts': []}
        with tempfile.TemporaryDirectory() as directory, patch.object(core, 'ROOT', Path(directory)), patch.object(subprocess, 'Popen', side_effect=launch), patch('builtins.input', side_effect=['1','2','1','2','1','2','0']), contextlib.redirect_stdout(io.StringIO()):
            with sessao_luz.open_channel(Path(directory), ('111','TEST_TOKEN'), '222') as channel:
                luz.run_menu(channel, report)
            saved = (Path(directory)/'resultado_luz_yoosee.json').read_text()
        self.assertEqual([p.returncode for p in children], [0])
        self.assertEqual([a['status'] for a in report['attempts']], ['response_received'] * 2)
        self.assertTrue(json.loads(saved)['summary']['both_transitions_observed'])
        self.assertNotIn('TEST_TOKEN', saved)

    def test_failure_after_first_command_preserves_both_results(self):
        channel = Mock()
        failure = result()
        failure.update(exit_code=43, events=[{'stage':'light_error','code':21000}])
        channel.send.side_effect = [result({'type':11}), failure]
        report = {'attempts': []}
        with patch('builtins.input', side_effect=['1','2','1','2','1','1']), patch.object(luz,'save_report'), contextlib.redirect_stdout(io.StringIO()):
            luz.run_menu(channel, report)
        self.assertEqual(channel.send.call_count, 2)
        self.assertEqual(report['attempts'][1]['sdk']['events'][0]['code'], 21000)
        self.assertFalse(luz.summarize_attempts(report['attempts'])['both_transitions_observed'])

    def test_accepted_reply_without_observation_is_incomplete(self):
        channel = Mock()
        channel.send.return_value = result({'type':11,'errCode':0})
        report = {'attempts': []}
        with patch('builtins.input',side_effect=['1','','','0']),patch.object(luz,'save_report'),contextlib.redirect_stdout(io.StringIO()):
            luz.run_menu(channel, report)
        self.assertFalse(luz.summarize_attempts(report['attempts'])['both_transitions_observed'])

    def test_interruption_keeps_attempt_and_does_not_retry(self):
        channel = Mock()
        channel.send.side_effect = KeyboardInterrupt
        report = {'attempts': []}
        with patch('builtins.input',side_effect=['1','2']),patch.object(luz,'save_report'),contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(KeyboardInterrupt):luz.run_menu(channel, report)
        channel.send.assert_called_once_with('on')
        self.assertEqual(report['attempts'][0]['status'],'interrupted_or_local_error')


if __name__=='__main__':unittest.main()
