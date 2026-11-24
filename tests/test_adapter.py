import sys,unittest,json,hashlib,re,struct
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import iniciar as app

class Response:
    def __init__(self,obj):self.raw=json.dumps(obj).encode()
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def read(self,n):return self.raw[:n]
class Opener:
    def __init__(self,obj):self.obj=obj;self.requests=[]
    def open(self,request,timeout):self.requests.append(request);return Response(self.obj)

class AdapterTests(unittest.TestCase):
    def test_email_wire_format(self):
        body=app.login_body('a@example.org','abc','55','client','app','token')
        self.assertEqual(body['pwd'], '900150983cd24fb0d6963f7d28e17f72')
        self.assertEqual(body['loginMode'],'email');self.assertEqual(body['email'],'a@example.org')
        self.assertNotIn('mobile',body);self.assertEqual(body['appVersion'],'10')
        self.assertEqual(body['terminalOS'],1)
    def test_mobile(self):
        body=app.login_body('11999999999','abc','55','c','a','t')
        self.assertEqual((body['mobileArea'],body['mobile'],body['loginMode']),('55','11999999999','mobile'))
    def test_precision(self):
        for value in ('18446744073709551615',18446744073709551615):
            self.assertEqual(app.parse_login({'code':0,'data':{'accessId':value,'accessToken':'SECRET'}}),(str(value),'SECRET'))
    def test_bad_sessions(self):
        for value in (True,1.2,'0','-9223372036854775809','18446744073709551616','1\n2',None):
            with self.subTest(value=value),self.assertRaises(app.TestError):
                app.parse_login({'code':0,'data':{'accessId':value,'accessToken':'SECRET'}})
        for token in ('a\nb','',None,'é','a\tb'):
            with self.subTest(token=token),self.assertRaises(app.TestError):
                app.parse_login({'code':0,'data':{'accessId':'123','accessToken':token}})
    def test_rejection_no_retry_or_secret_in_error(self):
        opener=Opener({'code':123,'msg':'PRIVATE_TOKEN user@example.org'})
        with self.assertRaises(app.TestError) as cm:app.authenticate({'pwd':'PRIVATE_PASSWORD'},opener)
        self.assertEqual(len(opener.requests),1)
        self.assertNotIn('PRIVATE',str(cm.exception));self.assertNotIn('@',str(cm.exception))
    def test_tls_endpoint_and_success(self):
        opener=Opener({'code':0,'data':{'accessId':'123','accessToken':'SECRET'}})
        self.assertEqual(app.authenticate({'pwd':'hashed'},opener),('123','SECRET'))
        self.assertEqual(opener.requests[0].full_url,app.LOGIN_URL)
        self.assertEqual(opener.requests[0].method,'POST')
    def test_redirect_is_not_followed(self):
        self.assertIsNone(app.NoRedirect().redirect_request(None,None,302,'',{},'https://other.example'))
    def test_report_allowlist(self):
        raw=b'SECRET\n{"stage":"session_online","code":0,"token":"SECRET"}\n{"stage":"SECRET","code":0}\n{"stage":"sdk_loaded","code":true}\n'
        result=app.parse_events(raw)
        self.assertEqual(result,[{'stage':'session_online','code':0}]);self.assertNotIn('SECRET',json.dumps(result))
    def test_native_hash_matches(self):
        source=(app.ROOT/'src/adapter.cpp').read_text()
        body=re.search(r'const unsigned char sdk_hash\[\]=\{([^}]+)\}',source).group(1)
        self.assertEqual(bytes(int(v,16) for v in body.split(',')).hex(),app.SDK_HASH)
    def test_binary_is_x64_pe(self):
        b=(app.ROOT/'yoosee_adapter.exe').read_bytes();pe=struct.unpack_from('<I',b,60)[0]
        self.assertEqual(b[pe:pe+4],b'PE\0\0');self.assertEqual(struct.unpack_from('<H',b,pe+4)[0],0x8664)


class ResponseDiagnosticTests(unittest.TestCase):
    def test_string_code_success(self):
        d={};self.assertEqual(app.parse_login({'code':'0','data':{'accessId':'123','accessToken':'SECRET'}},d),('123','SECRET'))
        self.assertEqual(d['reason'],'session_fields_valid')
    def test_string_error_not_confused_with_parse_failure(self):
        d={}
        with self.assertRaises(app.TestError) as cm:app.parse_login({'code':'123','msg':'SECRET'},d)
        self.assertEqual(cm.exception.status,'auth_rejected');self.assertEqual(d['server_code'],123)
    def test_schema_cannot_leak_values_or_unknown_keys(self):
        d={}
        with self.assertRaises(app.TestError):app.parse_login({'code':0,'data':{'accessId':'123','accessToken':None,'SECRET':'SECRET'},'user@private.org':'SECRET'},d)
        text=json.dumps(d)
        for private in ('SECRET','user@private.org','123'):self.assertNotIn(private,text)
        self.assertEqual(d['reason'],'access_token_type')
    def test_missing_code_reason(self):
        d={}
        with self.assertRaises(app.TestError):app.parse_login({'msg':'SECRET'},d)
        self.assertEqual(d['reason'],'code_missing_or_invalid')
    def test_non_json_reason(self):
        class NonJson(Opener):
            def open(self,*a,**kw):
                r=Response({});r.raw=b'<html>SECRET</html>';return r
        d={}
        with self.assertRaises(app.TestError):app.authenticate({},NonJson({}),d)
        self.assertEqual(d['reason'],'body_not_json');self.assertNotIn('SECRET',json.dumps(d))

class SignedIdTests(unittest.TestCase):
    def test_signed_ids_preserve_native_bits(self):
        for supplied in ('-1','-9223372036854775808','-1234567890123456789',-1234567890123456789):
            with self.subTest(supplied=supplied):
                d={};value,_=app.parse_login({'code':0,'data':{'accessId':supplied,'accessToken':'SECRET'}},d)
                self.assertEqual(struct.pack('<Q',int(value)),struct.pack('<q',int(supplied)))
                self.assertEqual(d['access_id_encoding'],'signed_negative')
                self.assertNotIn(str(supplied),json.dumps(d))
    def test_decimal_whitespace_plus_and_leading_zeros(self):
        for supplied in (' +123 ','000123'):
            value,_=app.parse_login({'code':0,'data':{'accessId':supplied,'accessToken':'SECRET'}})
            self.assertEqual(value,'123')
    def test_non_decimal_is_not_silently_truncated(self):
        for supplied in ('123abc','1e18','0x123','--1'):
            d={}
            with self.assertRaises(app.TestError):app.parse_login({'code':0,'data':{'accessId':supplied,'accessToken':'SECRET'}},d)
            self.assertEqual(d['access_id_encoding'],'non_decimal')

if __name__=='__main__':unittest.main()
