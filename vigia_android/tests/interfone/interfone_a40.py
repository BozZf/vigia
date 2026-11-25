"""Teste de referência do interfone no app Yoosee. Python 3, ADB, sem dependências."""
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time

BASE = Path(__file__).resolve().parent
PACKAGE = 'com.yoosee'


def locate_adb():
    for path in (BASE / 'adb.exe', shutil.which('adb'),
                 Path(os.environ.get('LOCALAPPDATA', '.')) / 'Android/Sdk/platform-tools/adb.exe',
                 Path(r'E:\Arquivos\Downloads\platform-tools-latest-windows\platform-tools\adb.exe')):
        if path and Path(path).is_file():
            return str(path)
    value = input('Caminho completo para adb.exe (ou para a pasta platform-tools): ').strip().strip('"')
    path = Path(value)
    if path.is_dir():
        path = path / 'adb.exe'
    if not path.is_file():
        raise ValueError('adb.exe não encontrado.')
    return str(path)


def run(adb, *args):
    return subprocess.run([adb, *args], capture_output=True, text=True, encoding='utf-8',
                          errors='replace', timeout=20)


def device_pid(adb):
    result = run(adb, 'shell', 'pidof', '-s', PACKAGE)
    value = result.stdout.strip()
    if not re.fullmatch(r'[1-9][0-9]*', value):
        raise ValueError('Abra o vídeo da A29 no Yoosee e execute o teste novamente.')
    return value


def summarize(lines, since, pid):
    """Allowlisted descriptions only. Discard every original message."""
    events = []
    for line in lines:
        match = re.match(r'^\s*(\d+(?:\.\d+)?)\s+(\d+)\s+\d+\s+[VDIWEFA]\s+(.*)$', line)
        if not match or float(match[1]) < since or match[2] != pid:
            continue
        body = match[3].lower()
        event = ''
        if 'gwmonitorplayer' in body:
            result = re.search(r'\b(stalktalk|starttalk|stoptalk) result code:\s*(-?\d{1,8})\b', body)
            if result:
                action = 'parar' if result[1] == 'stoptalk' else 'iniciar'
                event = f'GwMonitorPlayer · resposta ao {action}, código {result[2]}'
            elif re.search(r'\b(stalktalk|starttalk)\b', body):
                event = 'GwMonitorPlayer · iniciar fala'
            elif 'stoptalk' in body:
                event = 'GwMonitorPlayer · parar fala'
            elif 'player status not status_play' in body:
                event = 'GwMonitorPlayer · vídeo fora do estado de reprodução'
        elif 'gmonitorplayer' in body and re.search(r'\b(starttalk|stoptalk)\b', body):
            event = 'GMonitorPlayer · comando de fala'
        elif 'audiocaptureimpl' in body:
            if 'stop audio capture' in body:
                event = 'AudioCaptureImpl · captura encerrada'
            elif 'start failure' in body or 'startfromjni failure' in body or 'new audiorecord error' in body:
                event = 'AudioCaptureImpl · falha de captura'
            elif 'start open tx aec' in body:
                event = 'AudioCaptureImpl · preparação do áudio'
        if event and event not in events:
            events.append(event)
    return events


def main():
    adb = locate_adb()
    state = run(adb, 'get-state')
    if state.stdout.strip() != 'device':
        raise ValueError('Conecte somente o A40 por USB e autorize a depuração na tela do celular.')
    input('Abra a A29 ao vivo no Yoosee, deixe o interfone solto e pressione Enter no PC. ')
    pid = device_pid(adb)
    since = int(run(adb, 'shell', 'date', '+%s').stdout.strip()) + 1
    time.sleep(1.2)
    print('AGORA: use o interfone no Yoosee e diga “Teste do A40, um, dois, três”.')
    input('Ao terminar, solte ou desligue o interfone e pressione Enter no PC. ')
    if device_pid(adb) != pid:
        raise ValueError('O Yoosee reiniciou durante o teste. Repita com o vídeo já aberto.')
    log = run(adb, 'logcat', '-d', '-v', 'epoch', '--pid='+pid)
    events = summarize(log.stdout.splitlines(), since, pid) if log.returncode == 0 else []
    choices = {'s':'sim', 'n':'não', 'i':'inconclusivo'}
    while True:
        answer = input('A frase saiu do alto-falante da câmera? [s/n/i] ').strip().lower()
        if answer in choices:
            break
    report = ['Vigia · referência de interfone Android', 'Aplicativo testado: Yoosee',
              'Frase ouvida fisicamente na A29: '+choices[answer]]
    report += events or ['Implementação não identificada pelos eventos disponíveis.']
    if log.returncode:
        report.append('Leitura de eventos indisponível neste aparelho.')
    with tempfile.NamedTemporaryFile(mode='w', prefix='resultado_interfone_A40_', suffix='.txt',
                                     encoding='utf-8', dir=BASE, delete=False) as output:
        output.write('\n'.join(report)+'\n')
    print('\n'.join(report), '\nRelatório:', output.name)


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, subprocess.SubprocessError, EOFError) as error:
        raise SystemExit('Teste interrompido: '+str(error)) from None
