"""Yoosee Windows 1.0.0.14: experimental login + native SDK session probe.
Python standard library only. Reports contain only fixed status labels and integer codes.
"""
from __future__ import annotations
import ctypes
import datetime as dt
import getpass
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parent
EXE_HASH = 'ee6a499befe3d4ad62f79f9dd103f783a560852e6ed629629ba9c23e6727e333'
SDK_HASH = 'ec07cb4b98bc486e8bdb058c8695d16f0fb2c524be50dd8c9d0f0cfa87fa0990'
LOGIN_URL = 'https://openapi-iot.cloudlinks.cn/openapi/app/user/login/account'
STAGES = frozenset('arguments_invalid path_invalid sdk_hash_mismatch sdk_verified search_path_failed load_failed sdk_loaded factory_missing factory_null factory_ready initial_state probe_ok session_input_invalid registration_started session_state session_online session_rejected session_timeout unregister_requested native_exception'.split())
STAGES = STAGES | frozenset('device_input_invalid message_factory_missing message_factory_null message_factory_ready property_query_started property_sent property_ack property_received property_error property_error_category property_response_too_large property_timeout'.split())
STAGES = STAGES | frozenset('light_command_started light_sent light_ack light_received light_error light_error_category light_response_too_large light_timeout'.split())

STATE_NAMES = {-10:'ociosa', -1:'encerrando',0:'conectando',1:'online',2:'offline',3:'token recusado',4:'falha de inicializacao',5:'identificador invalido',6:'sessao desconectada pelo servidor',7:'acesso desativado',12:'dispositivo reativado',13:'token expirado',14:'falha ao decodificar token',15:'falha na verificacao do token',16:'token divergente',17:'terminal invalido'}

class TestError(Exception):
    def __init__(self, status, message, code=None):
        super().__init__(message);self.status=status;self.code=code


def sha256(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()


def pe_string(blob, rva, max_length):
    """Bounded PE section mapping; no execution of the vendor executable."""
    if blob[:2]!=b'MZ':raise ValueError('PE')
    pe=struct.unpack_from('<I',blob,0x3c)[0]
    if blob[pe:pe+4]!=b'PE\0\0':raise ValueError('PE')
    machine,count=struct.unpack_from('<HH',blob,pe+4)
    if machine!=0x8664 or count>96:raise ValueError('architecture')
    optlen=struct.unpack_from('<H',blob,pe+20)[0];section=pe+24+optlen
    for i in range(count):
        virtual_size,va,size,off=struct.unpack_from('<IIII',blob,section+i*40+8)
        if va<=rva<va+size:
            start=off+rva-va;data=blob[start:min(start+max_length+1,off+size)]
            if b'\0' not in data:raise ValueError('unterminated')
            return data.split(b'\0',1)[0].decode('ascii')
    raise ValueError('RVA')


def client_config(folder):
    exe=folder/'Yoosee.exe';sdk=folder/'IOT_LIB.dll'
    if not exe.is_file() or not sdk.is_file():
        raise TestError('installation_missing','Escolha a pasta que contem Yoosee.exe e IOT_LIB.dll.')
    if sha256(exe)!=EXE_HASH or sha256(sdk)!=SDK_HASH:
        raise TestError('version_mismatch','A versao instalada difere do Yoosee 1.0.0.14 analisado. O teste parou antes de carregar a DLL.')
    b=exe.read_bytes()
    # Client identifiers embedded in this exact vendor build, not account credentials.
    app_id=pe_string(b,0x5beb48,32);app_token=pe_string(b,0x5beb80,64)
    if not re.fullmatch('[a-f0-9]{32}',app_id) or not re.fullmatch('[a-f0-9]{64}',app_token):
        raise TestError('client_config_invalid','Nao foi possivel ler a configuracao desta versao.')
    return app_id,app_token


def login_body(account,password,area,client_id,app_id,app_token):
    account=account.strip()
    if not account or not password:raise TestError('input_invalid','Conta e senha sao obrigatorias.')
    try:password_bytes=password.encode('latin-1')
    except UnicodeEncodeError:
        raise TestError('input_invalid','Este teste ainda nao suporta caracteres fora de Latin-1 na senha.') from None
    body={'language':'en','pkgName':'Yoosee.PC','terminalOS':1,'appVersion':'10','apiVersion':'10','appName':'Yoosee.PC','appId':app_id,'appToken':app_token,'action':'account','uniqueId':client_id,'pwd':hashlib.md5(password_bytes).hexdigest()}
    if '@' in account:
        body.update(loginMode='email',email=account)
    else:
        if not account.isascii() or not account.isdigit() or not area.isascii() or not area.isdigit():
            raise TestError('input_invalid','Use o e-mail da conta ou telefone com DDD, sem espacos, e codigo de pais numerico.')
        body.update(loginMode='mobile',mobile=account,mobileArea=area)
    return body


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        return None


def json_type(value):
    return {dict:'object',list:'array',str:'string',int:'integer',float:'number',bool:'boolean',type(None):'null'}.get(type(value),'other')


def response_shape(reply):
    # Fixed field names and type labels only: never arbitrary keys or values.
    result={'root_type':json_type(reply)}
    fields=('code','data','result','error','msg','message','accessId','accessToken','accessid','access_token','AccessID','AccessToken')
    if isinstance(reply,dict):
        result['root_fields']={k:json_type(reply[k]) for k in fields if k in reply}
        if isinstance(reply.get('data'),dict):
            result['data_fields']={k:json_type(reply['data'][k]) for k in fields if k in reply['data']}
    return result


def parse_login(reply, diagnostic=None):
    diagnostic=diagnostic if diagnostic is not None else {}
    diagnostic.update(response_shape(reply))
    def invalid(reason,message):
        diagnostic['reason']=reason
        raise TestError('auth_response_invalid',message)
    if not isinstance(reply,dict):
        invalid('root_not_object','A resposta de login nao e um objeto JSON.')
    code=reply.get('code')
    # Some service versions encode result codes as decimal strings.
    if isinstance(code,str) and re.fullmatch(r'-?[0-9]{1,9}',code.strip()):code=int(code.strip())
    if type(code) is not int or not -(2**31)<=code<2**31:
        invalid('code_missing_or_invalid','A resposta nao trouxe um codigo de login reconhecivel.')
    diagnostic['server_code']=code
    if code!=0:
        diagnostic['reason']='server_rejected'
        raise TestError('auth_rejected','O login foi recusado (codigo %d). Nao houve nova tentativa automatica.'%code,code)
    data=reply.get('data')
    if not isinstance(data,dict):invalid('data_not_object','Resposta de login sem objeto de sessao.')
    access_id=data.get('accessId');token=data.get('accessToken')
    if type(access_id) not in (int,str):invalid('access_id_type','Identificador de sessao ausente ou em formato inesperado.')
    access_id=str(access_id).strip()
    if not re.fullmatch('[+-]?[0-9]{1,20}',access_id):
        diagnostic['access_id_encoding']='non_decimal'
        invalid('access_id_format','O identificador nao esta em formato decimal reconhecido.')
    numeric_id=int(access_id)
    if numeric_id==0 or not -(2**63)<=numeric_id<=2**64-1:
        diagnostic['access_id_encoding']='zero_or_out_of_range'
        invalid('access_id_format','Identificador fora do intervalo de 64 bits.')
    # Official Windows caller uses strtoll, then passes the same 64-bit bits
    # into the unsigned access_id member. Preserve negative IDs using modulo 2^64.
    diagnostic['access_id_encoding']='signed_negative' if numeric_id<0 else 'positive_decimal'
    access_id=str(numeric_id & ((1<<64)-1))
    if not isinstance(token,str):invalid('access_token_type','Token de sessao ausente ou em formato inesperado.')
    if not 1<=len(token)<=16384 or not token.isascii() or any(ord(c)<33 or ord(c)>126 for c in token):
        invalid('access_token_format','Token de sessao em formato inesperado.')
    diagnostic['reason']='session_fields_valid'
    return access_id,token


def authenticate(body, opener=None, diagnostic=None):
    diagnostic=diagnostic if diagnostic is not None else {}
    opener=opener or urllib.request.build_opener(NoRedirect())
    request=urllib.request.Request(LOGIN_URL,data=json.dumps(body,separators=(',',':')).encode(),headers={'Content-Type':'application/json; charset=utf-8'},method='POST')
    try:
        with opener.open(request,timeout=20) as response:
            status=getattr(response,'status',None)
            if type(status) is int:diagnostic['http_status']=status
            headers=getattr(response,'headers',{})
            content_type=headers.get('Content-Type','').split(';',1)[0].strip().lower()
            diagnostic['content_type']=content_type if content_type in ('application/json','text/json','text/html','text/plain') else 'other_or_missing'
            raw=response.read(1024*1024+1)
        if len(raw)>1024*1024:
            diagnostic['reason']='response_too_large'
            raise TestError('auth_response_invalid','Resposta de login maior que o limite esperado.')
        reply=json.loads(raw)
    except urllib.error.HTTPError as e:
        diagnostic['reason']='http_error';diagnostic['http_status']=e.code
        raise TestError('http_error','O servidor respondeu HTTP %d. Nenhuma repeticao foi feita.'%e.code,e.code) from None
    except (urllib.error.URLError,TimeoutError,OSError):
        diagnostic['reason']='network_error'
        raise TestError('network_error','Nao foi possivel concluir o login HTTPS. Confira a conexao com a internet.') from None
    except (ValueError,UnicodeError):
        diagnostic['reason']='body_not_json'
        raise TestError('auth_response_invalid','O servidor nao devolveu JSON valido. O relatorio indica o tipo de resposta, sem copiar seu conteudo.') from None
    return parse_login(reply,diagnostic)


def parse_events(raw):
    out=[]
    for line in raw.splitlines():
        try:obj=json.loads(line)
        except (ValueError,UnicodeError):continue
        if isinstance(obj,dict) and obj.get('stage') in STAGES and type(obj.get('code')) is int:
            out.append({'stage':obj['stage'],'code':obj['code']})
    return out


def validate_device_id(value):
    value=value.strip()
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,128}',value):
        raise TestError('device_input_invalid','Digite o ID da camera no app, sem espacos. Nao use IP, URL ou senha.')
    return value


def summarize_property(raw):
    result={'payload_received':False,'property_value_recognized':False}
    for line in raw.splitlines():
        try:obj=json.loads(line)
        except (ValueError,UnicodeError):continue
        if not isinstance(obj,dict) or obj.get('stage')!='property_payload':continue
        encoded=obj.get('hex')
        if not isinstance(encoded,str) or len(encoded)>131072 or not re.fullmatch(r'(?:[0-9a-f]{2})*',encoded):
            result['payload_format']='invalid_pipe_payload';continue
        payload=bytes.fromhex(encoded);result['payload_received']=True;result['response_bytes']=len(payload)
        try:value=json.loads(payload.rstrip(b'\0'))
        except (ValueError,UnicodeError):result['payload_format']='non_json';continue
        result['payload_format']='json';result['root_type']=json_type(value)
        if not isinstance(value,dict):continue
        code=value.get('code')
        if type(code) is int and -(2**31)<=code<2**31:
            result['response_code']=code
            if code!=0:continue
        # Only known wrappers; never traverse or expose arbitrary names or values.
        root=value.get('data',value)
        if not isinstance(root,dict):continue
        result['known_fields']={k:json_type(root[k]) for k in ('ProReadonly','ProReadonly._online','_online','stVal') if k in root}
        if 'ProReadonly' in root and isinstance(root['ProReadonly'],dict):
            node=root['ProReadonly'].get('_online')
        elif 'ProReadonly._online' in root:node=root['ProReadonly._online']
        elif '_online' in root:node=root['_online']
        else:node=root
        if not isinstance(node,dict) or 'stVal' not in node:continue
        state=node['stVal']
        result['state_value_type']=json_type(state)
        # Keep only a small state code, never string values or identifiers.
        if type(state) is int and -1<=state<=255:
            result['online_state_code']=state;result['property_value_recognized']=True
    return result


def summarize_light(raw):
    """Only explicit errCode=0 counts as a successful command response.

    The APK reads PenetrateRecDataEntity.errCode. Missing fields, ACK alone,
    unrelated types and arbitrary JSON must not become false success here.
    Physical state is collected separately in luz.py.
    """
    result={'payload_received':False,'command_response':'not_received'}
    for line in raw.splitlines():
        try:obj=json.loads(line)
        except (ValueError,UnicodeError):continue
        if not isinstance(obj,dict) or obj.get('stage')!='light_payload':continue
        encoded=obj.get('hex')
        if not isinstance(encoded,str) or len(encoded)>131072 or not re.fullmatch(r'(?:[0-9a-f]{2})*',encoded):
            result['payload_format']='invalid_pipe_payload';continue
        payload=bytes.fromhex(encoded)
        result.update(payload_received=True,response_bytes=len(payload),command_response='unrecognized')
        try:value=json.loads(payload.rstrip(b'\0'))
        except (ValueError,UnicodeError):result['payload_format']='non_json';continue
        result.update(payload_format='json',root_type=json_type(value))
        if not isinstance(value,dict):continue
        result['known_fields']={k:json_type(value[k]) for k in ('type','errCode') if k in value}
        response_type=value.get('type')
        if 'type' in value:
            if type(response_type) is not int or response_type!=11:
                result['type_matches']=False;continue
            result['type_matches']=True
            if 'errCode' not in value:
                result['command_response']='received'
                continue
        code=value.get('errCode')
        if type(code) is not int or not -(2**31)<=code<2**31:continue
        result['response_code']=code
        result['command_response']='accepted' if code==0 else 'rejected'
    return result


def native_test(folder,session=None,device=None,action=None):
    if action not in (None,'on','off'):
        raise TestError('action_invalid','Escolha ligar ou desligar a luz.')
    if action is not None and (session is None or device is None):
        raise TestError('session_input_invalid','O comando exige uma sessao e o ID da camera.')
    exe=ROOT/'yoosee_adapter.exe'
    if not exe.is_file():raise TestError('adapter_missing','O ZIP nao foi extraido por completo: falta yoosee_adapter.exe.')
    env=os.environ.copy();env['PATH']=str(folder)+os.pathsep+env.get('PATH','')
    payload=b'' if session is None else ('%s\n%s\n'%session).encode('ascii')
    if device is not None:
        if session is None:raise TestError('session_input_invalid','A consulta exige uma sessao autenticada.')
        payload+=(validate_device_id(device)+'\n').encode('ascii')
    mode='--probe' if session is None else ('--read' if device is not None else '--session')
    if action is not None:mode='--light-'+action
    def result_for(raw,exit_code,timed_out):
        result={'exit_code':exit_code,'timed_out':timed_out,'events':parse_events(raw)}
        if action is None:result['property']=summarize_property(raw)
        else:result.update(action=action,light=summarize_light(raw))
        return result
    with tempfile.TemporaryDirectory(prefix='yoosee_teste_') as working:
        proc=subprocess.Popen([str(exe),str(folder),mode],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,cwd=working,env=env,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        try:raw,_=proc.communicate(payload,timeout=15 if session is None else (65 if device is not None else 45))
        except subprocess.TimeoutExpired:
            proc.kill();raw,_=proc.communicate()
            return result_for(raw,-1,True)
        except BaseException:
            proc.kill();proc.communicate();raise
    return result_for(raw,proc.returncode,False)


def find_installation(interactive=True):
    candidates=[]
    for env in ('ProgramFiles','ProgramFiles(x86)','LOCALAPPDATA'):
        root=os.environ.get(env)
        if root:
            for tail in ('Yoosee','yoosee','Programs/Yoosee'):
                candidates.append(Path(root)/tail)
    try:
        import winreg
        for hive in (winreg.HKEY_LOCAL_MACHINE,winreg.HKEY_CURRENT_USER):
            for view in (winreg.KEY_WOW64_64KEY,winreg.KEY_WOW64_32KEY):
                try:
                    with winreg.OpenKey(hive,r'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall',0,winreg.KEY_READ|view) as key:
                        for i in range(winreg.QueryInfoKey(key)[0]):
                            try:
                                with winreg.OpenKey(key,winreg.EnumKey(key,i)) as sub:
                                    name=winreg.QueryValueEx(sub,'DisplayName')[0]
                                    if 'yoosee' in name.lower():
                                        path=winreg.QueryValueEx(sub,'InstallLocation')[0]
                                        if path:candidates.append(Path(path))
                            except OSError:pass
                except OSError:pass
    except ImportError:pass
    for p in candidates:
        if (p/'Yoosee.exe').is_file() and (p/'IOT_LIB.dll').is_file():return p.resolve()
    if not interactive:return None
    try:
        import tkinter as tk
        from tkinter import filedialog
        root=tk.Tk();root.withdraw()
        file=filedialog.askopenfilename(title='Selecione o Yoosee.exe instalado (versao 1.0.0.14)',filetypes=[('Yoosee','Yoosee.exe')])
        root.destroy()
        if file:return Path(file).resolve().parent
    except Exception:pass
    text=input('Cole o caminho da pasta onde o Yoosee esta instalado: ').strip().strip('"')
    if not text:raise TestError('cancelled','Teste cancelado.')
    p=Path(text).resolve()
    return p.parent if p.is_file() else p


def persistent_id():
    path=ROOT/'identificador_cliente.txt'
    try:return str(uuid.UUID(path.read_text().strip()))
    except (OSError,ValueError):
        value=str(uuid.uuid4());path.write_text(value,encoding='ascii');return value


def show_native_error(result):
    events=result['events'];failed=next((e for e in events if e['stage'] in ('load_failed','sdk_hash_mismatch','factory_missing','factory_null','native_exception')),None)
    if failed and failed['stage']=='load_failed':
        return 'A DLL nao carregou (erro Windows %d). Pode faltar uma dependencia do instalador.'%failed['code']
    if result['timed_out']:return 'O adaptador nao concluiu dentro do prazo e foi encerrado.'
    if not events:return 'O adaptador nao iniciou (codigo %s). O resultado identifica a falha de inicializacao.'%result['exit_code']
    return 'O SDK nao concluiu esta etapa. O resultado contem o ponto exato em que parou.'


def main():
    report={'version':'0.3.1','time_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'status':'started','camera_connection_tested':False,'camera_control_tested':False,'property_read_tested':False,'property_path':'ProReadonly._online'}
    rc=1
    print('\nYOOSEE - CONSULTA DO ESTADO DA CAMERA\n')
    print('Este teste le a propriedade de estado pelo SDK. Nao aciona luz, sirene ou PTZ.\n')
    try:
        if os.name!='nt' or struct.calcsize('P')!=8:
            raise TestError('platform_unsupported','Execute no Windows com Python 64 bits.')
        folder=find_installation()
        app_id,app_token=client_config(folder)
        print('Versao conferida. Testando carregamento e interface nativa...')
        probe=native_test(folder);report['probe']=probe
        if probe['exit_code']!=0 or not any(e['stage']=='probe_ok' for e in probe['events']):
            raise TestError('probe_failed',show_native_error(probe))
        print('DLL carregada e interface inicializada.\n')
        print('Use o ID da camera mostrado no app Yoosee, nao o nome personalizado ou IP.')
        device=validate_device_id(input('ID da camera: '))
        print('Agora digite a conta usada no app Yoosee (nao a senha NVR/ONVIF).')
        account=input('E-mail ou telefone com DDD: ').strip()
        if not account:raise TestError('cancelled','Login cancelado; o teste da DLL ficou registrado.')
        area='55' if '@' in account else (input('Codigo do pais [55]: ').strip() or '55')
        password=getpass.getpass('Senha da conta (nao aparece enquanto voce digita): ')
        body=login_body(account,password,area,persistent_id(),app_id,app_token)
        password='';account=''
        print('Autenticando no servico Yoosee...')
        report['auth_diagnostic']={}
        try:session=authenticate(body,diagnostic=report['auth_diagnostic'])
        finally:body.clear()
        report['authentication']='accepted'
        print('Login aceito. Conectando e consultando o estado (ate 60 segundos)...')
        try:result=native_test(folder,session,device)
        finally:session=None
        report['session']=result
        for event in result['events']:
            if event['stage']=='session_state':print('Estado:',STATE_NAMES.get(event['code'],'codigo %d'%event['code']))
        online=any(e['stage']=='session_online' for e in result['events'])
        query_started=any(e['stage']=='property_query_started' for e in result['events'])
        report['property_read_tested']=query_started
        prop=result['property']
        if online and result['exit_code']==0 and prop.get('property_value_recognized'):
            report['status']='property_read_confirmed';rc=0
            print('Consulta respondida. Codigo de estado registrado:',prop['online_state_code'])
            print('Esse estado pode vir do servico; ainda nao comprova conexao direta ou video ao vivo.')
        elif online and prop.get('payload_received'):
            report['status']='property_response_unrecognized'
            print('A consulta recebeu dados, mas o valor da propriedade nao foi reconhecido.')
        elif online:
            report['status']='property_read_failed' if query_started else 'property_setup_failed'
            print('A sessao IoT conectou, mas a consulta da propriedade nao foi concluida.')
            for event in result['events']:
                if event['stage'] in ('property_error','property_error_category','property_timeout'):
                    print(event['stage'],event['code'])
            print(show_native_error(result))
        else:
            report['status']='sdk_session_failed'
            print('A sessao do SDK nao foi confirmada online.');print(show_native_error(result))
    except TestError as e:
        report['status']=e.status
        if e.code is not None:report['error_code']=e.code
        print('\n'+str(e))
    except (EOFError,KeyboardInterrupt):
        report['status']='cancelled';print('\nTeste interrompido.')
    except Exception:
        report['status']='unexpected_local_error'
        print('\nOcorreu uma falha local inesperada. Nenhum detalhe de conta foi salvo.')
    target=ROOT/'resultado_yoosee.json'
    try:
        target.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print('\nEnvie somente este arquivo na conversa:\n'+str(target))
    except OSError:
        print('\nNao foi possivel salvar o resultado. Extraia o ZIP em uma pasta gravavel.')
    return rc

if __name__=='__main__':
    raise SystemExit(main())
