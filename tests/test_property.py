import json,sys,subprocess,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import iniciar as app

def wire(value):
    return json.dumps({'stage':'property_payload','hex':json.dumps(value).encode().hex()}).encode()+b'\n'

class PropertyTests(unittest.TestCase):
    def test_known_property_shapes(self):
        for data in ({'ProReadonly':{'_online':{'stVal':1}}},{'ProReadonly._online':{'stVal':1}},{'_online':{'stVal':1}},{'stVal':1},{'code':0,'data':{'ProReadonly._online':{'stVal':1}}}):
            with self.subTest(data=data):
                out=app.summarize_property(wire(data))
                self.assertTrue(out['property_value_recognized']);self.assertEqual(out['online_state_code'],1)
    def test_offline_is_successful_read_not_timeout(self):
        out=app.summarize_property(wire({'stVal':0}))
        self.assertTrue(out['property_value_recognized']);self.assertEqual(out['online_state_code'],0)
    def test_ack_alone_is_not_property_data(self):
        out=app.summarize_property(b'{"stage":"property_ack","code":0}\n')
        self.assertFalse(out['payload_received']);self.assertFalse(out['property_value_recognized'])
    def test_error_response_is_not_property_success(self):
        out=app.summarize_property(wire({'code':123,'stVal':1}))
        self.assertFalse(out['property_value_recognized']);self.assertEqual(out['response_code'],123)
    def test_malformed_payloads(self):
        for encoded in ('not hex','0','ab'*65537):
            out=app.summarize_property(json.dumps({'stage':'property_payload','hex':encoded}).encode())
            self.assertFalse(out['property_value_recognized'])
        out=app.summarize_property(b'{"stage":"property_payload","hex":"ff"}')
        self.assertEqual(out['payload_format'],'non_json')
    def test_unknown_response_retains_no_values_or_arbitrary_keys(self):
        data={'camera-secret-id':'sensitive','accessToken':'secret-token','ProReadonly':{'_online':{'stVal':'secret-token'},'ssid':'my-network'}}
        out=app.summarize_property(wire(data));text=json.dumps(out)
        for secret in ('camera-secret-id','sensitive','secret-token','my-network','ssid','accessToken'):self.assertNotIn(secret,text)
        self.assertFalse(out['property_value_recognized'])
        self.assertEqual(app.parse_events(wire(data)),[])
    def test_no_arbitrary_integers_or_primitive_success(self):
        for data in ({'stVal':12345678901},{'stVal':True},1,0,{'unrelated':{'stVal':1}}):
            self.assertFalse(app.summarize_property(wire(data))['property_value_recognized'])
    def test_device_input_rejects_urls_ip_newlines(self):
        for bad in ('','192.168.2.100','rtsp://host','12\n34','x'*129):
            with self.assertRaises(app.TestError):app.validate_device_id(bad)
        self.assertEqual(app.validate_device_id(' 1234567890 '),'1234567890')
    def test_worker_routes_secrets_via_pipe_and_filters_result(self):
        raw=wire({'stVal':1,'secret':'private'})+b'{"stage":"property_received","code":37}\n'
        class Worker:
            returncode=0
            def communicate(self,payload,timeout):
                self.payload=payload;self.timeout=timeout;return raw,None
        worker=Worker()
        with patch.object(app.subprocess,'Popen',return_value=worker) as popen:
            out=app.native_test(Path('.'),('111','TOKEN_SECRET'),'222')
        args=popen.call_args.args[0]
        self.assertEqual(args[-1],'--read');self.assertNotIn('TOKEN_SECRET',str(args))
        self.assertEqual(worker.payload,b'111\nTOKEN_SECRET\n222\n');self.assertEqual(worker.timeout,65)
        self.assertNotIn('private',json.dumps(out));self.assertNotIn('TOKEN_SECRET',json.dumps(out))
        self.assertTrue(out['property']['property_value_recognized'])
    def test_worker_timeout_kills_process(self):
        class Worker:
            returncode=-1
            calls=0
            killed=False
            def communicate(self,*a,**kw):
                self.calls+=1
                if self.calls==1:raise subprocess.TimeoutExpired('worker',65)
                return b'',None
            def kill(self):self.killed=True
        worker=Worker()
        with patch.object(app.subprocess,'Popen',return_value=worker):out=app.native_test(Path('.'),('111','SECRET'),'222')
        self.assertTrue(worker.killed);self.assertTrue(out['timed_out']);self.assertFalse(out['property']['property_value_recognized'])

if __name__=='__main__':unittest.main()
