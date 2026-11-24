"""Windows live preview using the installed Yoosee 1.0.0.14 player."""
import datetime as dt
import getpass
import json
import os
from queue import Empty, Queue
import struct
import subprocess
import tempfile
from threading import Thread
from time import monotonic
import iniciar as core

PLAYER_HASH = '622e31d0428182d53edbabeb53aab7e095ac944053a1b90ff9d379cc8b75c2d2'
AUDIO_STAGES = {'audio_listen','audio_output_open','audio_output_write','talk_requested',
                'talk_setup_error','talk_setup_timeout','mic_format_unsupported','talk_start_result','talk_start_reply','talk_end_result','talk_end_reply',
                'mic_capture_ms','mic_encoder_drained','mic_open','mic_started','mic_error','mic_frames','mic_first_frame','mic_frame_error'}
VIDEO_STAGES = AUDIO_STAGES | {'ptz_direction','ptz_send_result','video_window_ready','video_player_created','video_view_attached','video_library_missing','video_create_failed','video_setup_failed',
                'video_play_return','video_state','video_closed','preview_light'}


def save(report):
    path = core.ROOT/'resultado_video_yoosee.json'
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(report, indent=2), encoding='utf-8')
    tmp.replace(path)


def collect(proc, report):
    lines = Queue()
    def read():
        try:
            for line in proc.stdout:
                lines.put(line)
        finally:
            lines.put(None)
    thread = Thread(target=read, daemon=True)
    thread.start()
    startup_deadline = monotonic() + 75
    opened = False
    try:
        while True:
            if not opened and monotonic() >= startup_deadline:
                raise core.TestError('startup_timeout','A abertura do vídeo excedeu 75 segundos.')
            try:
                line = lines.get(timeout=.5)
            except Empty:
                continue
            if line is None:
                break
            try:
                event = json.loads(line)
            except (ValueError,UnicodeError):
                continue
            if not isinstance(event,dict):
                continue
            stage, code = event.get('stage'), event.get('code')
            if not isinstance(stage,str) or stage not in core.STAGES | VIDEO_STAGES or type(code) is not int:
                continue
            report['events'].append({'stage':stage,'code':code})
            if stage=='video_play_return':
                opened = True
            save(report)
        return proc.wait(timeout=5)
    finally:
        if proc.poll() is None:
            proc.kill()
        proc.wait()
        thread.join()


def audio_observations(report):
    attempted = False
    questions = (
        ('audio_listen', 1, 'camera_to_pc', 'Você ouviu no PC o som feito perto da câmera?'),
        ('talk_requested', 0, 'pc_to_camera', 'Você ouviu na câmera a frase dita no microfone do PC?'),
    )
    for stage, code, direction, question in questions:
        if any(e['stage']==stage and e['code']==code for e in report['events']):
            attempted = True
            answer = input(question+' [s/n/Enter=pular] ').strip().lower()
            report.setdefault('audio_observed', {})[direction] = {'s':'yes','n':'no'}.get(answer,'unknown')
            save(report)
    return attempted


def main():
    report = {'version':'0.4.4','time_utc':dt.datetime.now(dt.timezone.utc).isoformat(),
              'status':'starting','events':[],'live_image_observed':'unknown'}
    print('Yoosee | Vídeo ao vivo 0.4.4')
    try:
        if os.name != 'nt' or struct.calcsize('P') != 8:
            raise core.TestError('platform_unsupported','Use o Windows com Python de 64 bits.')
        folder = core.find_installation()
        app_id, app_token = core.client_config(folder)
        player = folder/'GWPlayerLibV1.dll'
        if not player.is_file() or core.sha256(player) != PLAYER_HASH:
            raise core.TestError('player_version_mismatch','Selecione a instalação do Yoosee 1.0.0.14 usada no teste da luz.')
        device = core.validate_device_id(input('ID da câmera: '))
        account = input('E-mail ou telefone da conta Yoosee: ').strip()
        area = '55' if '@' in account else (input('Código do país [55]: ').strip() or '55')
        body = core.login_body(account,getpass.getpass('Senha da conta: '),area,core.persistent_id(),app_id,app_token)
        print('Autenticando e abrindo a câmera…',flush=True)
        report['auth_diagnostic'] = {}
        try:
            session = core.authenticate(body,diagnostic=report['auth_diagnostic'])
        finally:
            body.clear()
        report['status']='opening'
        save(report)
        env=os.environ.copy()
        env['PATH']=str(folder)+os.pathsep+env.get('PATH','')
        with tempfile.TemporaryDirectory(prefix='yoosee_video_') as cwd:
            with subprocess.Popen([str(core.ROOT/'yoosee_adapter.exe'),str(folder),'--video'],
                                  stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
                                  cwd=cwd,env=env,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0)) as proc:
                try:
                    proc.stdin.write(('%s\n%s\n%s\n' % (*session,device)).encode('ascii'))
                    proc.stdin.close()
                except BrokenPipeError:
                    pass
                report['exit_code']=collect(proc,report)
        closed = any(e['stage']=='video_closed' for e in report['events'])
        report['status']='closed' if closed and report['exit_code']==0 else 'player_failed'
        save(report)
        tested_audio=audio_observations(report)
        directions=('esquerda','direita','cima','baixo')
        tested={e['code'] for e in report['events'] if e['stage']=='ptz_direction'}
        if tested:
            report['movement_observed']={}
            for index, name in enumerate(directions):
                if index in tested:
                    answer=input(f'A câmera se moveu para {name}? [s/n/Enter=pular] ').strip().lower()
                    report['movement_observed'][name]={'s':'yes','n':'no'}.get(answer,'unknown')
                    save(report)
        elif not tested_audio and any(e['stage']=='video_play_return' for e in report['events']):
            answer=input('Quais imagens apareceram ao vivo? [2=ambas distintas, c=só a de cima, b=só a de baixo, r=repetidas, n=nenhuma, Enter=pular] ').strip().lower()
            report['lens_observation']={'2':'both_distinct','c':'upper_only','b':'lower_only',
                                        'r':'duplicated','n':'none'}.get(answer,'unknown')
            report['live_image_observed']={'2':'yes','c':'yes','b':'yes','r':'yes','n':'no'}.get(answer,'unknown')
        if report['status']=='player_failed':
            print('O reprodutor encerrou com erro. O relatório indica a última etapa.')
    except core.TestError as err:
        report['status']=err.status
        if err.code is not None:report['error_code']=err.code
        print(err)
    except (KeyboardInterrupt,EOFError):
        report['status']='interrupted'
    except (OSError,subprocess.SubprocessError):
        report['status']='local_error'
        print('Falha local ao executar a prévia.')
    finally:
        try:
            save(report)
            print('Relatório:',core.ROOT/'resultado_video_yoosee.json')
        except OSError:
            print('Não foi possível salvar o relatório na pasta extraída.')
    return 0 if report['status']=='closed' else 1


if __name__=='__main__':raise SystemExit(main())
