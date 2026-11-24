"""Vigia desktop camera panel. The authenticated SDK runs in a separate process."""
import ctypes
from ctypes import wintypes
import datetime as dt
import json
import os
from pathlib import Path
import queue
import struct
import subprocess
import tempfile
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox
import uuid

import iniciar as core
import panel_store as store
import drive_upload as drive
import daily_recording as daily
from panel_widgets import PALETTES, Tile, typeface
from video import PLAYER_HASH

ROOT = Path(__file__).resolve().parent
APP = Path(os.getenv('LOCALAPPDATA', Path.home()))/'Vigia'
NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)


class Panel:
    def __init__(self, root, home=APP):
        self.root,self.home=root,home
        self.home.mkdir(parents=True,exist_ok=True)
        self.prefs=store.read_json(home/'preferencias.json',{})
        self.theme=self.prefs.get('theme','escuro')
        if self.theme not in PALETTES:self.theme='escuro'
        self.p=PALETTES[self.theme];self.face=typeface(root)
        self.styles=[];self.tiles=[];self.q=queue.Queue()
        self.proc=None;self.worker_hwnd=0;self.connected=False;self.connecting=False
        self.terminating=False;self.leaving=False;self.decode_busy=False
        self.alert=False;self.light=False;self.talking=False;self.listening=False;self.busy=False
        self.job=None;self.want_record=False;self.record_day=None;self.stopping=False
        self.retry_due=0;self.retry_delay=5;self.resume_intent=False;self.lost_since=0;self.record_retry_at=0
        self.drive_cancel=threading.Event();self.linking=False
        self.processing=False;self.settings_win=None;self.working=None;self.session_dir=None
        self.status=tk.StringVar(value='Entre para acessar sua câmera.')
        self.connection=tk.StringVar(value='Desconectado')
        self.auth_attempt=0;self.session_key=0
        self.stats={'version':'0.5.1','events':[]}
        self.auto=tk.BooleanVar(value=bool(self.prefs.get('auto_record')))
        self.remember=tk.BooleanVar()
        self.fields={k:tk.StringVar(value='55' if k=='area' else '') for k in ('account','password','device','area')}
        try:
            saved=store.load_login(home/'login.dat')
            for k,var in self.fields.items():
                if isinstance(saved.get(k),str):var.set(saved[k])
            self.remember.set(bool(saved))
        except (OSError,ValueError,TypeError):
            self.status.set('O Windows não conseguiu abrir o login salvo. Entre novamente.')
        root.title('Vigia  ·  Câmeras')
        sw,sh=root.winfo_screenwidth(),root.winfo_screenheight()
        root.geometry(f'{min(1160,sw-40)}x{min(790,sh-85)}')
        root.minsize(min(840,sw-40),min(585,sh-85))
        root.protocol('WM_DELETE_WINDOW',lambda:self.disconnect(True))
        self.shell()
        self.show_login();self.apply_theme();self.controls()
        root.after(35,self.poll)
        root.after(2000,self.retry_deliveries)

    def styled(self,widget,**roles):
        self.styles.append((widget,roles))
        widget.configure(**{k:self.p[v] for k,v in roles.items()})
        return widget

    def frame(self,parent,role='bg',**kw):
        return self.styled(tk.Frame(parent,bd=0,**kw),bg=role)

    def label(self,parent,text='',role='bg',color='text',size=10,bold=False,var=None,**kw):
        return self.styled(tk.Label(parent,text=text,textvariable=var,font=(self.face,size,'bold' if bold else 'normal'),
                                    bd=0,anchor='w',**kw),bg=role,fg=color)
    def tile(self,parent,text,fn,glyph=None,**kw):
        return Tile(parent,self,text,fn,glyph,**kw)

    def check(self,parent,text,var,fn,role):
        w=tk.Checkbutton(parent,text=text,variable=var,command=fn,font=(self.face,10),bd=0,anchor='w',
                         takefocus=True,highlightthickness=0)
        return self.styled(w,bg=role,fg='text',activebackground=role,activeforeground='text',selectcolor='field')

    def apply_theme(self):
        self.p=PALETTES[self.theme]; self.root.configure(bg=self.p['bg'])
        self.styles=[(w,roles) for w,roles in self.styles if w.winfo_exists()]
        for w,roles in self.styles:w.configure(**{k:self.p[v] for k,v in roles.items()})
        self.tiles=[w for w in self.tiles if w.winfo_exists()]
        for w in self.tiles:w.draw()
        self.brandmark.delete('all')
        self.brandmark.create_oval(3,6,29,32,width=2,outline=self.p['accent'])
        self.brandmark.create_oval(10,13,22,25,width=2,outline=self.p['accent'])
        self.brandmark.create_oval(19,9,24,14,fill=self.p['accent'],outline='')

    def shell(self):
        self.root.grid_rowconfigure(0,weight=1);self.root.grid_columnconfigure(1,weight=1)
        side=self.frame(self.root,'side',width=156);side.grid(row=0,column=0,sticky='ns');side.pack_propagate(False)
        brand=self.frame(side,'side');brand.pack(fill='x',padx=14,pady=(20,36))
        self.brandmark=self.styled(tk.Canvas(brand,width=34,height=38,highlightthickness=0),bg='side')
        self.brandmark.pack(side='left')
        self.label(brand,'Vigia','side',size=20,bold=True).pack(side='left',padx=5)
        self.live_nav=self.tile(side,'Ao vivo',self.focus_live,'camera',kind='nav',role='side')
        self.live_nav.pack(fill='x',padx=10,pady=2);self.live_nav.selected=True
        self.tile(side,'Preferências',self.preferences,'settings',kind='nav',role='side').pack(fill='x',padx=10,pady=2)
        self.exit_button=self.tile(side,'Sair da conta',lambda:self.disconnect(False),'logout',kind='nav',role='side')
        self.exit_button.pack(side='bottom',fill='x',padx=10,pady=14)
        main=self.frame(self.root);main.grid(row=0,column=1,sticky='nsew')
        head=self.frame(main);head.pack(fill='x',padx=22,pady=(18,14))
        self.title=self.label(head,'Câmeras',size=21,bold=True);self.title.pack(side='left')
        self.badge=self.label(head,var=self.connection,role='panel',color='muted',padx=10,pady=5)
        self.badge.pack(side='right')
        self.body=self.frame(main);self.body.pack(fill='both',expand=True,padx=20)
        self.login=self.frame(self.body);self.dashboard=self.frame(self.body)
        self.build_login();self.build_live()
        self.label(main,var=self.status,color='muted',wraplength=685).pack(fill='x',padx=22,pady=10)

    def build_login(self):
        card=self.frame(self.login,'panel')
        card.place(relx=.5,rely=.48,anchor='center',width=400)
        inner=self.frame(card,'panel');inner.pack(fill='both',padx=27,pady=22)
        self.label(inner,'Entrar na câmera','panel',size=20,bold=True).pack(fill='x',pady=(0,12))
        for key,title in [('device','ID da câmera'),('account','E-mail ou telefone'),('password','Senha da conta Yoosee'),('area','Código do país (telefone)')]:
            self.label(inner,title,'panel',color='muted',size=9).pack(fill='x',pady=(5,3))
            w=tk.Entry(inner,textvariable=self.fields[key],show='•' if key=='password' else '',
                       font=(self.face,11),bd=0,highlightthickness=1,relief='flat')
            self.styled(w,bg='field',fg='text',insertbackground='text',highlightbackground='line',highlightcolor='accent')
            w.pack(fill='x',ipady=5);w.bind('<Return>',lambda e:self.connect())
        self.check(inner,'Manter login neste Windows',self.remember,self.remember_changed,'panel').pack(fill='x',pady=8)
        self.enter=self.tile(inner,'Entrar',self.connect,kind='primary',height=39);self.enter.pack(fill='x')

    def build_live(self):
        self.dashboard.grid_columnconfigure(0,weight=1);self.dashboard.grid_rowconfigure(0,weight=1)
        views=self.frame(self.dashboard);views.grid(row=0,column=0,sticky='nsew')
        views.grid_columnconfigure(0,weight=1)
        self.hosts=[]
        for i,label in enumerate(('Lente superior','Lente inferior')):
            views.grid_rowconfigure(i,weight=1,uniform='view')
            card=self.frame(views,'panel');card.grid(row=i,column=0,sticky='nsew',pady=(0,8 if i==0 else 0))
            bar=self.frame(card,'panel');bar.pack(fill='x',padx=12,pady=6)
            self.label(bar,label,'panel',size=10,bold=True).pack(side='left')
            stage=self.frame(card,'black');stage.pack(fill='both',expand=True,padx=2,pady=(0,2))
            host=tk.Frame(stage,bg='#101115',bd=0,highlightthickness=0)
            host.place(relx=.5,rely=.5,anchor='center')
            def fit(e,h=host):
                w=max(1,min(e.width,int(e.height*16/9)));h.place_configure(width=w,height=max(1,int(w*9/16)))
            stage.bind('<Configure>',fit);self.hosts.append(host)
        controls=self.frame(self.dashboard,'panel',width=222)
        controls.grid(row=0,column=1,sticky='ns',padx=(12,0));controls.grid_propagate(False)
        controls.grid_columnconfigure(0,weight=1)
        self.label(controls,'Controles','panel',size=14,bold=True).grid(row=0,column=0,sticky='w',padx=13,pady=(14,9))
        self.actions={}
        for row,(key,label,glyph,fn) in enumerate([
            ('light','Luz branca','bulb',lambda:self.send(2 if self.light else 1)),
            ('sound','Ouvir câmera','speaker',lambda:self.send(7)),
            ('talk','Falar por 5 s','mic',lambda:self.send(8)),
            ('alert','Expulsão','alert',self.toggle_alert)],1):
            btn=self.tile(controls,label,fn,glyph);btn.grid(row=row,column=0,sticky='ew',padx=12,pady=3);self.actions[key]=btn
        self.label(controls,'Movimento','panel',size=10,bold=True).grid(row=5,column=0,sticky='w',padx=14,pady=(12,2))
        pad=self.frame(controls,'panel');pad.grid(row=6,column=0,pady=2)
        self.arrows=[]
        for r,c,key,glyph in [(0,1,5,'up'),(1,0,3,'left'),(1,2,4,'right'),(2,1,6,'down')]:
            b=self.tile(pad,'',lambda k=key:self.send(k),glyph,width=47,height=29);b.grid(row=r,column=c,padx=1,pady=1);self.arrows.append(b)
        self.label(controls,'Gravações','panel',size=10,bold=True).grid(row=7,column=0,sticky='w',padx=14,pady=(12,4))
        self.record=self.tile(controls,'Gravar',self.toggle_record,'record')
        self.record.grid(row=8,column=0,sticky='ew',padx=12,pady=3)
        self.tile(controls,'Abrir pasta',self.open_files,'folder',height=32).grid(row=9,column=0,sticky='ew',padx=12,pady=(2,8))

    def show_login(self):
        self.dashboard.pack_forget();self.login.pack(fill='both',expand=True)
        self.title.configure(text='Câmeras')

    def show_live(self):
        self.login.pack_forget();self.dashboard.pack(fill='both',expand=True)
        self.title.configure(text='Câmera ao vivo');self.root.update_idletasks()

    def focus_live(self):
        if self.settings_win and self.settings_win.winfo_exists():self.settings_win.destroy()
        self.root.focus_set()

    def save_prefs(self):
        try:store.write_json(self.home/'preferencias.json',self.prefs)
        except OSError:messagebox.showerror('Preferências','Falha ao salvar as preferências deste Windows.',parent=self.root)

    def remember_changed(self):
        if not self.remember.get():
            try:(self.home/'login.dat').unlink(missing_ok=True)
            except OSError:
                messagebox.showerror('Login','O Windows não conseguiu apagar o login salvo.',parent=self.root);return False
        return True

    def preferences(self):
        if self.settings_win and self.settings_win.winfo_exists():
            self.settings_win.lift();return
        w=self.settings_win=tk.Toplevel(self.root);w.title('Preferências · Vigia');w.transient(self.root)
        w.resizable(False,False)
        self.styled(w,bg='panel')
        box=self.frame(w,'panel');box.pack(padx=24,pady=18,fill='both',expand=True)
        self.label(box,'Preferências','panel',size=18,bold=True).pack(fill='x')
        def section(txt):self.label(box,txt,'panel',size=10,bold=True).pack(fill='x',pady=(15,5))
        section('Aparência')
        themes=self.frame(box,'panel');themes.pack(fill='x')
        choices={}
        def choose(t):
            self.theme=t;self.prefs['theme']=t;self.save_prefs()
            for k,b in choices.items():b.selected=k==t
            self.apply_theme()
        for t in PALETTES:
            b=self.tile(themes,t.capitalize(),lambda k=t:choose(k),width=145)
            b.selected=t==self.theme;b.pack(side='left',fill='x',expand=True,padx=2);choices[t]=b
        section('Áudio da expulsão')
        self.sound_name=tk.StringVar(value=self.prefs.get('audio_name','Nenhum áudio escolhido'))
        self.label(box,var=self.sound_name,role='panel',color='muted',wraplength=370).pack(fill='x')
        self.tile(box,'Escolher áudio…',self.choose_audio,'audio').pack(fill='x',pady=3)
        section('Destino das gravações')
        self.tile(box,'Conectar Google Drive…',self.link_drive,'folder').pack(fill='x',pady=3)
        self.dest_label=tk.StringVar(value=self.destination_text())
        self.label(box,var=self.dest_label,role='panel',color='muted',wraplength=370).pack(fill='x')
        self.label(box,'Use o Drive direto com OAuth ou uma pasta já sincronizada no PC.','panel','muted',9,wraplength=370,justify='left').pack(fill='x',pady=3)
        row=self.frame(box,'panel');row.pack(fill='x')
        self.tile(row,'Vincular pasta…',self.choose_cloud,'folder',width=170).pack(side='left',fill='x',expand=True)
        self.tile(row,'Desvincular',lambda:self.set_cloud(''),width=114).pack(side='left',padx=(5,0))
        self.label(box,'Arquivos diários até 00h · retenção de 7 datas','panel','muted',9).pack(fill='x',pady=2)
        self.check(box,'Gravar ao conectar',self.auto,self.set_auto,'panel').pack(fill='x',pady=4)
        section('Conta neste computador')
        self.tile(box,'Esquecer login salvo',self.forget,'logout').pack(fill='x')
        self.apply_theme()

    def forget(self):
        self.remember.set(False)
        if not self.remember_changed():return
        self.fields['password'].set('')
        self.status.set('Login salvo removido.')
    def set_auto(self):
        self.prefs['auto_record']=self.auto.get();self.save_prefs()
    def choose_cloud(self):
        dest=filedialog.askdirectory(parent=self.settings_win,title='Escolha a pasta sincronizada')
        if dest:self.set_cloud(dest)
    def set_cloud(self,dest):
        self.drive_cancel.set()
        try:(self.home/'drive.dat').unlink(missing_ok=True)
        except OSError:self.status.set('Falha ao desvincular o Drive.');return
        self.prefs.pop('drive_folder',None)
        self.prefs['cloud']=dest;self.save_prefs();self.dest_label.set(self.destination_text())
        self.status.set('Destino aplicado aos próximos clipes.')
    def destination_text(self):
        if self.prefs.get('drive_folder'):return 'Google Drive / Vigia - Gravações'
        return self.prefs.get('cloud') or 'Somente neste computador'

    def link_drive(self):
        if self.linking:return
        f=filedialog.askopenfilename(parent=self.settings_win,title='Cliente OAuth do Google (app para computador)',filetypes=[('Cliente OAuth','*.json')])
        if not f:return
        self.linking=True;self.drive_cancel=threading.Event()
        cancel=self.drive_cancel
        self.status.set('Autorize o Vigia no navegador.');self.dest_label.set('Aguardando autorização no navegador…')
        def run():
            try:folder=drive.link(Path(f),self.home/'drive.dat',cancel)
            except (OSError,ValueError,KeyError) as e:self.q.put(('drive_link',(None,str(e))))
            else:self.q.put(('drive_link',(folder,None)))
        threading.Thread(target=run,daemon=True).start()

    def open_files(self):
        path=self.home/'Gravações';path.mkdir(exist_ok=True)
        os.startfile(str(path))
    def choose_audio(self):
        if self.alert or self.decode_busy:
            self.status.set('Aguarde o fim da importação ou pare a expulsão para trocar o áudio.');return
        path=filedialog.askopenfilename(parent=self.settings_win or self.root,title='Áudio para a câmera',
             filetypes=[('Áudio','*.wav *.mp3 *.m4a *.aac *.wma *.flac'),('Todos','*.*')])
        if not path:return
        self.decode_busy=True;self.status.set('Preparando áudio…')
        def convert():
            tmp=self.home/('audio-'+uuid.uuid4().hex+'.tmp')
            try:
                subprocess.run([str(ROOT/'yoosee_adapter.exe'),'--decode-audio',path,str(tmp)],check=True,creationflags=NO_WINDOW)
                if not tmp.stat().st_size:raise ValueError()
                os.replace(tmp,self.home/'alert.pcm')
                self.q.put(('audio_ready',Path(path).name))
            except (OSError,ValueError,subprocess.SubprocessError):
                self.q.put(('audio_ready',None))
            finally:tmp.unlink(missing_ok=True)
        threading.Thread(target=convert,daemon=True).start()

    def connect(self,resuming=False):
        if self.connecting or self.proc or self.terminating:return
        self.retry_due=0;self.resume_intent=resuming;self.auth_attempt+=1
        attempt=self.auth_attempt
        try:
            if os.name!='nt' or struct.calcsize('P')!=8:raise ValueError('Use Python de 64 bits no Windows.')
            fields={k:v.get() for k,v in self.fields.items()}
            fields['device']=core.validate_device_id(fields['device'])
            folder=Path(self.prefs['sdk']) if self.prefs.get('sdk') else None
            if not folder or not (folder/'Yoosee.exe').is_file():folder=core.find_installation(interactive=False)
            if not folder:
                f=filedialog.askopenfilename(parent=self.root,title='Localize o Yoosee instalado',filetypes=[('Yoosee','Yoosee.exe')])
                if not f:return
                folder=Path(f).parent
        except (ValueError,core.TestError) as e:self.status.set(str(e));return
        self.connecting=True;self.controls();self.connection.set('Conectando');self.status.set('Autenticando a conta Yoosee…')
        def auth():
            try:
                app_id,app_token=core.client_config(folder)
                if core.sha256(folder/'GWPlayerLibV1.dll')!=PLAYER_HASH:raise ValueError('Versão do reprodutor incompatível.')
                body=core.login_body(fields['account'],fields['password'],fields['area'],core.persistent_id(),app_id,app_token)
                try:session=core.authenticate(body)
                finally:body.clear()
                self.q.put(('auth',(attempt,(folder,session,fields))))
            except (OSError,ValueError,core.TestError) as e:self.q.put(('auth_error',(attempt,str(e))))
            except Exception:self.q.put(('auth_error',(attempt,'Falha ao autenticar a conta.')))
        threading.Thread(target=auth,daemon=True).start()

    def launch(self,args):
        folder,session,fields=args
        if self.terminating:return
        if self.remember.get():
            try:store.save_login(self.home/'login.dat',fields)
            except OSError:messagebox.showerror('Login','O Windows não conseguiu salvar o login.',parent=self.root)
        self.prefs['sdk']=str(folder);self.save_prefs()
        self.want_record=self.resume_intent or self.auto.get()
        self.lost_since=time.monotonic();self.record_retry_at=0
        self.show_live()
        self.working=tempfile.TemporaryDirectory(prefix='vigia-')
        self.session_dir=self.home/'Gravações'/(dt.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')+'_'+uuid.uuid4().hex[:6])
        (self.session_dir/'clips').mkdir(parents=True)
        env=os.environ.copy();env['PATH']=str(folder)+os.pathsep+env.get('PATH','')
        env.update(YOOSEE_HOST_A=str(self.hosts[0].winfo_id()),YOOSEE_HOST_B=str(self.hosts[1].winfo_id()),
                   YOOSEE_ALERT_PATH=str(self.home/'alert.pcm'),YOOSEE_CLIPS_PATH=str(self.session_dir/'clips'))
        self.proc=subprocess.Popen([str(ROOT/'yoosee_adapter.exe'),str(folder),'--video'],stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,cwd=self.working.name,env=env,creationflags=NO_WINDOW)
        self.session_key+=1;key=self.session_key;proc=self.proc
        self.stats={'version':'0.5.1','events':[]}
        self.status.set('Abrindo as duas lentes…')
        def reader():
            try:
                for line in proc.stdout:
                    try:e=json.loads(line)
                    except (ValueError,UnicodeError):continue
                    if isinstance(e,dict):self.q.put(('native',(key,e)))
            finally:
                self.q.put(('end',(key,proc.wait())))
        threading.Thread(target=reader,daemon=True).start()
        try:proc.stdin.write(('%s\n%s\n%s\n'%(*session,fields['device'])).encode('ascii'))
        finally:proc.stdin.close()
        self.controls()

    def send(self,cmd):
        if not self.proc or not self.worker_hwnd:return False
        post=ctypes.windll.user32.PostMessageW
        post.argtypes=[wintypes.HWND,wintypes.UINT,wintypes.WPARAM,wintypes.LPARAM]
        ok=bool(post(self.worker_hwnd,0x8000+50,cmd,0))
        if not ok:self.status.set('O reprodutor não recebeu o comando.')
        return ok

    def toggle_alert(self):
        if self.alert:self.send(9);return
        if self.decode_busy:self.status.set('Aguarde a preparação do áudio.');return
        if not (self.home/'alert.pcm').is_file():
            self.preferences();self.choose_audio();return
        self.send(9)

    def toggle_record(self):
        if self.want_record:
            self.want_record=False
            if self.job and not self.stopping:self.stop_clip()
        else:
            self.want_record=True;self.begin_clip()
        self.controls()
    def begin_clip(self):
        if not self.connected or self.leaving or self.job:return
        self.record_day=dt.date.today()
        try:self.job=store.make_job(self.session_dir,self.prefs.get('cloud'),Path(self.working.name),self.prefs.get('drive_folder'),day=self.record_day)
        except OSError:
            self.want_record=False;self.status.set('Falha ao preparar a pasta de gravações.');return
        self.stopping=False;self.record_retry_at=0
        if not self.send(10):
            self.job.unlink(missing_ok=True);self.job=None;self.want_record=False
    def stop_clip(self):
        self.stopping=self.send(12)
        if self.stopping:self.stop_at=time.monotonic()
    def completed_clip(self):
        if self.job:
            store.finish_job(self.job)
            if not daily.media(self.job):
                self.record_retry_at=time.monotonic()+15
                self.status.set('A câmera encerrou sem gerar vídeo.')

            self.job=None
        self.stopping=False;self.record_day=None
        self.retry_deliveries(schedule=False)
        if self.want_record and self.connected and not self.leaving and not self.record_retry_at:self.begin_clip()
        self.controls()

    def retry_deliveries(self,schedule=True):
        if not self.processing:
            self.processing=True
            def deliver():
                msg=None
                try:
                    jobs=sorted((self.home/'Gravações').glob('*/*.json'))
                    def send(job,data,sources):drive.upload(job,data,sources,self.home/'drive.dat')
                    def trash(job,data):drive.trash_expired(job,data,self.home/'drive.dat')
                    today=dt.date.today()
                    # Expire outstanding receipts before starting large uploads.
                    def old(job):
                        data=store.read_json(job,{})
                        try:return data.get('policy')=='daily-v1' and daily.expired(data['day'],today)
                        except (KeyError,ValueError):return False
                    for job in sorted(jobs,key=lambda j:not old(j)):
                        if self.job==job:continue
                        try:
                            data=store.read_json(job,{})
                            if job.parent!=self.session_dir and time.time()-job.stat().st_mtime>300:
                                store.recover_finalized(job)
                            if data.get('policy')=='daily-v1':
                                state=daily.maintain(job,dt.date.today(),send,trash)
                                if state=='expired':msg='Retenção de sete dias aplicada.'
                                if state=='delivered':msg='Envio ao Drive confirmado.' if data.get('drive_folder') else 'Gravação diária salva no destino.'
                            elif store.deliver(job,send):
                                msg='Clipe anterior salvo no destino.'
                        except (OSError,ValueError,KeyError):
                            msg='Há uma entrega ou limpeza pendente. O Vigia tentará novamente.'
                finally:self.q.put(('delivery',msg))
            threading.Thread(target=deliver,daemon=True).start()
        if schedule:self.root.after(30000,self.retry_deliveries)

    def controls(self):
        usable=self.connected and not self.leaving
        self.enter.state(enabled=not self.connecting and not self.proc)
        self.exit_button.state(enabled=bool(self.proc or self.retry_due or self.resume_intent) and not self.leaving)
        self.actions['light'].state(text='Luz ligada' if self.light else 'Luz branca',active=self.light,enabled=usable and not self.busy and not self.alert)
        self.actions['sound'].state(text='Silenciar câmera' if self.listening else 'Ouvir câmera',active=self.listening,enabled=usable and not self.talking and not self.alert)
        self.actions['talk'].state(text='Parar interfone' if self.talking and not self.alert else 'Falar por 5 s',active=self.talking and not self.alert,enabled=usable and not self.alert)
        self.actions['alert'].state(text='Parar expulsão' if self.alert else 'Expulsão',active=self.alert,enabled=usable and (self.alert or (not self.talking and not self.busy)))
        for b in self.arrows:b.state(enabled=usable and not self.busy and not self.alert)
        self.record.state(text='Parar gravação' if self.want_record else 'Finalizando…' if self.job else 'Gravar 24 h',
                          active=self.want_record,enabled=usable and (self.want_record or not self.job))

    def native(self,e):
        stage,code=e.get('stage'),e.get('code')
        if stage=='panel_ready':
            if type(code)!=int or code<=0:return
            self.worker_hwnd=code
            if self.leaving:self.send(11)
            return
        if stage=='light_payload':
            self.light_reply=core.summarize_light(json.dumps(e).encode()).get('command_response')
            return
        if not isinstance(stage,str) or type(code)!=int:return
        if stage in ('mic_capture_ms','mic_frames','mic_first_frame','talk_start_reply','talk_end_result','alert_state',
                     'alert_audio_started','video_state','record_started','record_completed','record_error','clip_finalized','panel_light_error'):
            if len(self.stats['events'])>=2000:del self.stats['events'][:250]
            self.stats['events'].append({'stage':stage,'code':code})
        if stage=='video_state':
            was=self.connected;self.connected=code==5;self.connecting=not self.connected and code!=10
            self.connection.set('Ao vivo' if self.connected else 'Sem sinal' if code==10 else 'Conectando')
            if self.connected:self.status.set('Câmera conectada.')
            if not self.connected:
                if not self.lost_since:self.lost_since=time.monotonic()
                if self.job and not self.stopping:self.stop_clip()
            else:
                self.lost_since=0;self.retry_delay=5;self.resume_intent=False
                if not was and self.want_record and not self.job and not self.leaving:self.begin_clip()
        elif stage=='control_busy':
            self.busy=bool(code)
            if code in (1,2):self.light_reply=None
        elif stage=='light_state':
            if getattr(self,'light_reply',None) in ('received','accepted'):self.light=bool(code)
            else:
                self.status.set('A câmera não confirmou o comando de luz.')
                if self.alert:self.send(9)
        elif stage=='panel_light_error':self.status.set('Falha ao alterar a luz. Confira a imagem.')
        elif stage=='audio_listen':self.listening=bool(code)
        elif stage=='talk_active':
            self.talking=bool(code)
            if not self.talking:self.status.set('Interfone encerrado.')
        elif stage=='talk_seconds':self.status.set(f'Fale agora ({code} s).')
        elif stage=='alert_state':
            self.alert=bool(code);self.status.set('Expulsão ativa.' if code else 'Expulsão encerrada.')
        elif stage=='alert_audio_started':self.status.set('Expulsão ativa · reproduzindo o áudio na câmera.')
        elif stage in ('talk_setup_error','talk_setup_timeout','mic_error','mic_frame_error','panel_command_error'):
            self.status.set('O controle não conseguiu concluir a operação.')
            if stage=='panel_command_error' and code in (10,12):self.want_record=False;self.completed_clip()
        elif stage=='record_started':self.status.set('Gravando até 00h · retenção de 7 dias.')
        elif stage=='record_completed':self.completed_clip()
        elif stage=='record_error':
            self.record_retry_at=time.monotonic()+15;self.status.set(f'O gravador retornou erro {code}.')
            if self.job and not self.stopping:self.stop_clip()
        elif stage=='record_stop_result' and code:self.status.set(f'Falha ao fechar o clipe ({code}).')
        elif stage not in ('mic_started','mic_frames'):return
        self.controls()

    def disconnect(self,exit_app):
        self.terminating=exit_app
        self.retry_due=0;self.resume_intent=False;self.want_record=False;self.auth_attempt+=1
        if not self.proc:self.connecting=False
        if exit_app:self.drive_cancel.set()
        if not self.proc:
            if exit_app:self.root.destroy()
            else:self.status.set('Reconexão cancelada.');self.controls()
            return
        if self.leaving:return
        self.leaving=True;self.want_record=False;self.status.set('Encerrando a câmera…');self.controls()
        self.send(11)
        self.shutdown_at=time.monotonic()
    def schedule_reconnect(self):
        self.resume_intent=True;self.retry_due=time.monotonic()+self.retry_delay
        self.status.set(f'Gravação interrompida. Reconectando em {self.retry_delay} s…')
        self.retry_delay=min(120,self.retry_delay*2)

    def ended(self,rc):
        resume=self.want_record and not self.leaving and not self.terminating
        self.connected=False;self.connecting=False;self.want_record=False
        if self.job:self.completed_clip()
        self.proc=None;self.worker_hwnd=0;self.leaving=False
        self.alert=self.light=self.talking=self.listening=self.busy=False
        if self.working:
            try:self.working.cleanup()
            except OSError:pass
            self.working=None
        self.stats['exit_code']=rc
        try:store.write_json(ROOT/'resultado_painel_yoosee.json',self.stats)
        except OSError:pass
        if self.terminating:self.root.destroy();return
        if not resume and not self.remember.get():self.fields['password'].set('')
        self.connection.set('Desconectado');self.status.set('Sessão encerrada.' if rc==0 else f'O reprodutor encerrou com código {rc}.')
        if resume:self.schedule_reconnect()
        self.show_login();self.controls()

    def poll(self):
        for _ in range(200):
            try:k,v=self.q.get_nowait()
            except queue.Empty:break
            if k in ('auth','auth_error'):
                attempt,v=v
                if attempt!=self.auth_attempt:continue
            if k=='auth':
                try:self.launch(v)
                except (OSError,ValueError) as e:
                    if self.proc:self.disconnect(False)
                    else:self.ended(1)
                    self.status.set(f'Falha ao abrir a câmera. {e}')
            elif k=='auth_error':
                self.connecting=False;self.connection.set('Desconectado');self.status.set(v);self.controls()
                if self.resume_intent:self.schedule_reconnect()
            elif k=='native' and v[0]==self.session_key:self.native(v[1])
            elif k=='end' and v[0]==self.session_key:
                self.ended(v[1])
                if self.terminating:return
            elif k=='audio_ready':
                self.decode_busy=False
                if v:
                    self.prefs['audio_name']=v;self.save_prefs()
                    if hasattr(self,'sound_name'):self.sound_name.set(v)
                self.status.set('Áudio pronto. Clique em Expulsão para iniciar.' if v else 'Este arquivo não pôde ser lido. Tente um WAV ou MP3.')
            elif k=='drive_link':
                self.linking=False
                folder,error=v
                if folder and not self.drive_cancel.is_set():
                    self.prefs['drive_folder']=folder;self.prefs['cloud']='';self.save_prefs()
                    if hasattr(self,'dest_label'):self.dest_label.set(self.destination_text())
                    self.status.set('Google Drive vinculado para os próximos clipes.')
                elif error:
                    self.status.set(error)
                    if hasattr(self,'dest_label'):self.dest_label.set(self.destination_text())
            elif k=='delivery':
                self.processing=False
                if v and not self.alert:self.status.set(v)
        self.recording_tick(dt.date.today(),time.monotonic())
        if self.proc and self.leaving and time.monotonic()-self.shutdown_at>150:
            self.proc.terminate()
        self.root.after(40,self.poll)

    def recording_tick(self,today,now):
        if self.job and self.want_record and not self.stopping and self.record_day and today>self.record_day:
            self.stop_clip()
        if self.stopping and self.job and now-self.stop_at>15:
            self.status.set('Finalizando o arquivo diário…')
        if self.connected and self.want_record and not self.job and self.record_retry_at and now>=self.record_retry_at:
            self.begin_clip()
        if self.proc and self.want_record and self.lost_since and now-self.lost_since>45 and not self.leaving:
            if self.worker_hwnd:self.send(11)
            elif self.proc.poll() is None:self.proc.terminate()
            self.lost_since=now
        if self.retry_due and now>=self.retry_due and not self.proc and not self.terminating:
            self.connect(resuming=True)


if __name__=='__main__':
    win=tk.Tk()
    try:
        if os.name=='nt':
            mutex=ctypes.WinDLL('kernel32',use_last_error=True).CreateMutexW
            mutex.argtypes=[ctypes.c_void_p,wintypes.BOOL,wintypes.LPCWSTR];mutex.restype=wintypes.HANDLE
            handle=mutex(None,False,'Local\\VigiaPainelDesktop')
            if not handle:raise ctypes.WinError(ctypes.get_last_error())
            if ctypes.get_last_error()==183:
                win.withdraw();messagebox.showinfo('Vigia','O painel já está aberto.');win.destroy();raise SystemExit()
        Panel(win)
        win.mainloop()
    except Exception as err:
        messagebox.showerror('Vigia',f'Não foi possível abrir o painel. {err}')
