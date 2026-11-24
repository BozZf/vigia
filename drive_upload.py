"""Optional direct Google Drive upload, using a user-selected desktop OAuth client."""
import base64
import datetime as dt
from pathlib import Path
import hashlib
import json
import os
import secrets
import time
import urllib.error
import urllib.parse as parse
import urllib.request as web
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer

import panel_store as store

API='https://www.googleapis.com/drive/v3'
TOKEN='https://oauth2.googleapis.com/token'
SCOPE='https://www.googleapis.com/auth/drive.file'
CHUNK=4*1024*1024


class DriveError(OSError):
    pass


class NoRedirect(web.HTTPRedirectHandler):
    def redirect_request(self,*args):return None


def request(url,method='GET',data=None,headers=None,allowed=()):
    req=web.Request(url,data=data,method=method,headers=headers or {})
    try:
        response=web.build_opener(NoRedirect()).open(req,timeout=30)
    except web.HTTPError as e:
        if e.code not in allowed:
            e.close()
            raise DriveError(f'Google Drive retornou HTTP {e.code}.') from None
        response=e
    with response:
        return response.status,response.headers,response.read(1024*1024)


def token_request(fields):
    data=parse.urlencode(fields).encode()
    _,_,raw=request(TOKEN,'POST',data,{'Content-Type':'application/x-www-form-urlencoded'})
    parsed=json.loads(raw)
    if not parsed.get('access_token'):raise DriveError('O Google não concedeu acesso.')
    return parsed


def link(client_file,secret_path,cancel):
    app=json.loads(client_file.read_text(encoding='utf-8-sig')).get('installed',{})
    if not app.get('client_id') or not app.get('client_secret'):
        raise DriveError('Escolha um cliente OAuth do tipo App para computador.')
    verifier=secrets.token_urlsafe(48)
    challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
    state=secrets.token_urlsafe(32);result={}
    class Callback(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_GET(self):
            parts=parse.urlsplit(self.path);query=parse.parse_qs(parts.query)
            if parts.path!='/retorno' or query.get('state')!=[state]:
                self.send_error(404);return
            result['code']=query.get('code',[''])[0]
            self.send_response(200);self.send_header('Content-Type','text/plain; charset=utf-8')
            self.end_headers();self.wfile.write('Volte ao Vigia para ver o resultado.'.encode())
    with HTTPServer(('127.0.0.1',0),Callback) as server:
        redirect=f'http://127.0.0.1:{server.server_port}/retorno'
        params=dict(client_id=app['client_id'],response_type='code',redirect_uri=redirect,scope=SCOPE,
                    access_type='offline',prompt='consent',state=state,code_challenge=challenge,code_challenge_method='S256')
        if not webbrowser.open('https://accounts.google.com/o/oauth2/v2/auth?'+parse.urlencode(params)):
            raise DriveError('Não foi possível abrir o navegador.')
        server.timeout=.5
        end=time.monotonic()+180
        while not result and not cancel.is_set() and time.monotonic()<end:server.handle_request()
    if cancel.is_set() or not result.get('code'):raise DriveError('Vinculação cancelada ou expirada.')
    client={k:app[k] for k in ('client_id','client_secret')}
    tokens=token_request(dict(client,grant_type='authorization_code',code=result['code'],redirect_uri=redirect,code_verifier=verifier))
    if not tokens.get('refresh_token'):raise DriveError('O Google não concedeu acesso contínuo.')
    if cancel.is_set():raise DriveError('Vinculação cancelada.')
    auth={'Authorization':'Bearer '+tokens['access_token'],'Content-Type':'application/json'}
    _,_,raw=request(API+'/files?fields=id','POST',json.dumps({'name':'Vigia - Gravações','mimeType':'application/vnd.google-apps.folder'}).encode(),auth)
    folder=json.loads(raw)['id']
    if cancel.is_set():raise DriveError('Vinculação cancelada.')
    store.save_login(secret_path,dict(client,refresh_token=tokens['refresh_token'],folder=folder))
    return folder


def valid_session(url):
    u=parse.urlsplit(url)
    return u.scheme=='https' and u.hostname in ('www.googleapis.com','content.googleapis.com','upload.googleapis.com') and not u.username and not u.password and u.port in (443,None)


class LinkedDrive:
    def __init__(self, folder, secret_path):
        self.path=secret_path
        self.folder=folder
        self.token=self.refresh()

    def refresh(self):
        config=store.load_login(self.path)
        if not config or config.get('folder')!=self.folder:
            raise DriveError('O destino desta gravação está desvinculado.')
        keys={k:config[k] for k in ('client_id','client_secret','refresh_token')}
        return token_request(dict(keys,grant_type='refresh_token'))['access_token']

    def call(self,url,method='GET',data=None,headers=None,allowed=()):
        for attempt in range(2):
            hs=dict(headers or {},Authorization='Bearer '+self.token)
            reply=request(url,method,data,hs,allowed=(*allowed,401))
            if reply[0]!=401:return reply
            if not attempt:self.token=self.refresh()
        raise DriveError('O Drive não aceitou a credencial renovada.')


def marker(job,data):
    return {'vigiaRecording':job.stem,'vigiaDay':data['day'],'vigiaPolicy':'daily-v1'}


def remote_offset(headers, size):
    span=headers.get('Range','')
    if not span:return 0
    if not span.startswith('bytes=0-'):raise DriveError('Faixa de upload desconhecida.')
    value=int(span[8:])+1
    if not 0<value<=size:raise DriveError('Posição inválida no Drive.')
    return value


def upload(job,data,sources,secret_path):
    api=LinkedDrive(data['drive_folder'],secret_path)
    daily=data.get('policy')=='daily-v1'
    for source in sources:
        ids=data.setdefault('drive_ids',{})
        if source.name not in ids:
            _,_,raw=api.call(API+'/files/generateIds?count=1&space=drive')
            ids[source.name]=json.loads(raw)['ids'][0]
            store.write_json(job,data)
        remote=ids[source.name]
        url=API+'/files/'+parse.quote(remote,safe='')+'?fields=id,size,md5Checksum,parents,appProperties,trashed'
        size=source.stat().st_size
        key=hashlib.sha256(source.name.encode()).hexdigest()[:16]
        resume=job.with_name(job.stem+'.'+key+'.resume')
        def matches():
            code,_,raw=api.call(url,allowed=(404,))
            if code==404:return False
            meta=json.loads(raw)
            if daily and (meta.get('trashed') or data['drive_folder'] not in meta.get('parents',[]) or
                          any(meta.get('appProperties',{}).get(k)!=v for k,v in marker(job,data).items())):
                raise DriveError('O arquivo no Drive mudou de pasta ou identificação.')
            with source.open('rb') as f:md5=hashlib.file_digest(f,'md5').hexdigest()
            if int(meta.get('size',-1))!=size or meta.get('md5Checksum')!=md5:
                raise DriveError('O conteúdo no Drive difere da gravação local.')
            if daily:
                data.setdefault('drive_md5',{})[source.name]=md5
                store.write_json(job,data)
            resume.unlink(missing_ok=True)
            return True

        if matches():continue
        offset=0;session=None
        if daily and resume.exists():
            saved=store.load_login(resume)
            candidate=saved.get('session','')
            if saved.get('id')==remote and valid_session(candidate):
                rc,head,_=api.call(candidate,'PUT',b'',{'Content-Range':f'bytes */{size}'},allowed=(308,404,410))
                if rc in (200,201):
                    if matches():continue
                    raise DriveError('O arquivo final ainda não foi confirmado.')
                if rc==308:session,offset=candidate,remote_offset(head,size)
        if not session:
            name=source.name if daily else source.name[33:]
            meta={'id':remote,'name':name,'parents':[data['drive_folder']],'mimeType':'video/mp4'}
            if daily:meta['appProperties']=marker(job,data)
            hs={'Content-Type':'application/json','X-Upload-Content-Length':str(size),'X-Upload-Content-Type':'video/mp4'}
            _,head,_=api.call('https://www.googleapis.com/upload/drive/v3/files?uploadType=resumable','POST',json.dumps(meta).encode(),hs)
            session=head.get('Location','')
            if not valid_session(session):raise DriveError('Endereço de upload inválido.')
            if daily:store.save_login(resume,{'id':remote,'session':session})
        with source.open('rb') as f:
            while offset<size:
                if not secret_path.exists():raise DriveError('Envio interrompido após desvincular.')
                if daily and (dt.date.today()-dt.date.fromisoformat(data['day'])).days>=7:
                    raise DriveError('A gravação saiu da janela de retenção.')
                f.seek(offset);block=f.read(CHUNK);end=offset+len(block)
                if not block:raise DriveError('O clipe local foi alterado.')
                hs={'Content-Type':'video/mp4','Content-Range':f'bytes {offset}-{end-1}/{size}'}
                code,head,_=api.call(session,'PUT',block,hs,allowed=(308,))
                if code in (200,201):break
                next_offset=remote_offset(head,size)
                if not offset<next_offset<=end:raise DriveError('O Drive não confirmou o bloco enviado.')
                offset=next_offset
        if not matches():raise DriveError('O Drive ainda não confirmou o arquivo.')


def trash_expired(job,data,secret_path):
    api=LinkedDrive(data['drive_folder'],secret_path)
    for name,remote in data['drive_ids'].items():
        url=API+'/files/'+parse.quote(remote,safe='')
        rc,headers,raw=api.call(url+'?fields=id,appProperties,parents,trashed,md5Checksum',allowed=(404,))
        if rc==404:continue
        meta=json.loads(raw)
        if meta.get('trashed') or data['drive_folder'] not in meta.get('parents',[]):continue
        if any(meta.get('appProperties',{}).get(k)!=v for k,v in marker(job,data).items()):continue
        checksum=data.get('drive_md5',{}).get(name)
        if checksum and checksum!=meta.get('md5Checksum'):continue
        conditions={'Content-Type':'application/json'}
        etag=headers.get('ETag') or headers.get('etag')
        if etag:conditions['If-Match']=etag
        api.call(url+'?fields=id,trashed','PATCH',b'{"trashed":true}',conditions)
