"""Interactive white-light test. No camera command runs without menu selection."""
from __future__ import annotations
import datetime as dt
import getpass
import json
import os
import struct
import iniciar as core
from sessao_luz import open_channel

VERSION='0.3.3'


def observed_state(prompt):
    while True:
        value=input(prompt+' [1=acesa, 2=apagada, Enter=nao observei]: ').strip()
        if value in ('1','2',''):return {'1':'on','2':'off','':'unknown'}[value]
        print('Digite 1, 2 ou pressione Enter.')


def observation(action,before,after):
    return {
        'before':before,'after':after,
        'target_state_observed':after==action,
        'transition_observed':before in ('on','off') and before!=action and after==action,
    }


def summarize_attempts(attempts):
    observed={a['action'] for a in attempts if a.get('observation',{}).get('transition_observed')}
    return {
        'on_transition_observed':'on' in observed,
        'off_transition_observed':'off' in observed,
        'both_transitions_observed':observed=={'on','off'},
    }


def save_report(report):
    report['summary']=summarize_attempts(report['attempts'])
    target=core.ROOT/'resultado_luz_yoosee.json'
    pending=target.with_suffix('.tmp')
    pending.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    pending.replace(target)
    return target


def run_menu(channel, report):
    while True:
        print('\n1 - Ligar a luz branca\n2 - Desligar a luz branca\n0 - Sair e guardar o resultado')
        choice=input('Opcao: ').strip()
        if choice=='0':return
        if choice not in ('1','2'):
            print('Escolha 1, 2 ou 0.');continue
        action='on' if choice=='1' else 'off'
        before=observed_state('Antes do comando, a luz esta')
        attempt={'action':action,'status':'in_progress','time_utc':dt.datetime.now(dt.timezone.utc).isoformat(),
                 'observation':observation(action,before,'unknown')}
        report['attempts'].append(attempt)
        save_report(report)
        print('Enviando comando de '+('ligar' if action=='on' else 'desligar')+' (ate 65 segundos)...')
        try:result=channel.send(action)
        except BaseException:
            attempt['status']='interrupted_or_local_error'
            raise
        attempt['sdk']=result
        state=result['light']['command_response']
        attempt['status']='response_'+state
        save_report(report)
        if state=='accepted':
            print('Resposta do comando: errCode=0. Confira agora a luz na camera.')
        elif state=='rejected':
            print('Resposta do comando: erro',result['light']['response_code'])
        elif state=='received':
            print('Resposta recebida. Confira a luz na câmera.')
        elif state=='unrecognized':
            print('Recebi dados, mas o formato de resposta ainda nao foi reconhecido.')
        else:
            print('Nao recebi a resposta final do comando. Confira se a luz mudou mesmo assim.')
        if result['exit_code']!=0:print(core.show_native_error(result))
        after=observed_state('Depois do comando, a luz esta')
        attempt['observation']=observation(action,before,after)
        save_report(report)
        if after == 'unknown':
            print('Estado da luz pendente de observação.')
        elif after == 'on':
            print('Luz acesa, conforme sua observação.')
        else:
            print('Luz apagada, conforme sua observação.')
        if result['exit_code'] != 0:
            print('Sessão encerrada após a falha. O resultado desta tentativa foi salvo.')
            return


def main():
    report={'version':VERSION,'test':'white_light','status':'started',
            'time_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'attempts':[]}
    login_request = {}
    rc=1
    print('\nYOOSEE - TESTE DA LUZ BRANCA - '+VERSION+'\n')
    print('Escolha ligar ou desligar no menu e confira a luz fisicamente.')
    print('Sair do programa mantem a luz no estado atual.\n')
    try:
        if os.name!='nt' or struct.calcsize('P')!=8:
            raise core.TestError('platform_unsupported','Execute no Windows com Python 64 bits.')
        folder=core.find_installation()
        app_id,app_token=core.client_config(folder)
        print('Conferindo o adaptador e a instalacao do Yoosee...')
        probe=core.native_test(folder);report['probe']=probe
        if probe['exit_code']!=0 or not any(e['stage']=='probe_ok' for e in probe['events']):
            raise core.TestError('probe_failed',core.show_native_error(probe))
        device=core.validate_device_id(input('ID da camera mostrado no app: '))
        print('Use a conta e a senha do app Yoosee.')
        account=input('E-mail ou telefone com DDD: ').strip()
        if not account:raise core.TestError('cancelled','Login cancelado.')
        area='55' if '@' in account else (input('Codigo do pais [55]: ').strip() or '55')
        password=getpass.getpass('Senha da conta (oculta): ')
        login_request=core.login_body(account,password,area,core.persistent_id(),app_id,app_token)
        password='';account=''
        print('Autenticando para a sessão de luz...', flush=True)
        report['auth_diagnostic'] = {}
        session = core.authenticate(login_request, diagnostic=report['auth_diagnostic'])
        login_request.clear()
        report['authentication'] = 'accepted'
        report['connection_mode'] = 'persistent'
        print('Login aceito. Os comandos usarão a mesma sessão.', flush=True)
        with open_channel(folder, session, device) as channel:
            run_menu(channel, report)
        report['status']='on_and_off_observed' if summarize_attempts(report['attempts'])['both_transitions_observed'] else 'test_incomplete'
        rc=0
    except core.TestError as e:
        report['status']=e.status
        if e.code is not None:report['error_code']=e.code
        print('\n'+str(e))
    except (KeyboardInterrupt,EOFError):
        report['status']='interrupted';print('\nTeste interrompido.')
    except OSError:
        report['status']='local_io_error'
        print('\nFalha ao acessar um arquivo ou iniciar o adaptador. Use uma pasta extraida e gravavel.')
    except Exception:
        report['status']='unexpected_local_error';print('\nFalha local inesperada; o resultado registra a etapa alcancada.')
    finally:
        login_request.clear()
        try:print('\nEnvie este arquivo na conversa:\n'+str(save_report(report)))
        except OSError:print('\nNao foi possivel salvar o resultado. Extraia o ZIP em uma pasta gravavel.')
    return rc


if __name__=='__main__':raise SystemExit(main())
