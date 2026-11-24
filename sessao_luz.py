"""One native SDK registration for all light commands in the menu."""
from contextlib import contextmanager
import json
import os
from queue import Empty, Queue
import subprocess
import tempfile
from threading import Thread
from time import monotonic

import iniciar as core


class LightChannel:
    def __init__(self, process):
        self.process = process
        self.lines = Queue()
        self.reader = Thread(target=self._read_output, daemon=True)
        self.reader.start()

    def _read_output(self):
        try:
            for line in self.process.stdout:
                self.lines.put(line)
        finally:
            self.lines.put(None)

    def send(self, action):
        if action not in ('on', 'off'):
            raise ValueError('invalid light action')
        raw = bytearray()
        code = -1
        timed_out = False
        deadline = monotonic() + 65
        try:
            try:
                self.process.stdin.write((action + '\n').encode('ascii'))
                self.process.stdin.flush()
            except BrokenPipeError:
                pass  # Drain any startup diagnostics already in the output pipe.
            while True:
                line = self.lines.get(timeout=max(0, deadline - monotonic()))
                if line is None:
                    code = self.process.wait(timeout=2) or -1
                    break
                event = json.loads(line)
                if event.get('stage') == 'command_done':
                    code = int(event['code'])
                    break
                raw.extend(line)
        except (Empty, subprocess.TimeoutExpired):
            timed_out = True
            self.process.kill()
        return {'action': action, 'exit_code': code, 'timed_out': timed_out,
                'events': core.parse_events(bytes(raw)), 'light': core.summarize_light(bytes(raw))}


@contextmanager
def open_channel(folder, session, device):
    device = core.validate_device_id(device)
    env = os.environ.copy()
    env['PATH'] = str(folder) + os.pathsep + env.get('PATH', '')
    with tempfile.TemporaryDirectory(prefix='yoosee_luz_') as working:
        with subprocess.Popen([str(core.ROOT/'yoosee_adapter.exe'), str(folder), '--light-menu'],
                              stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                              cwd=working, env=env, creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0)) as proc:
            channel = LightChannel(proc)
            try:
                proc.stdin.write(('%s\n%s\n%s\n' % (*session, device)).encode('ascii'))
                proc.stdin.flush()
                yield channel
            finally:
                try:
                    proc.stdin.close()  # EOF releases the SDK registration.
                except BrokenPipeError:
                    pass
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
                channel.reader.join()
