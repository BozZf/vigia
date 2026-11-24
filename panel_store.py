"""Windows user settings, protected login, and delivery of finalized clips."""
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import shutil
import struct
import tempfile
import uuid


def atomic_bytes(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as f:
        tmp = Path(f.name)
        try:
            f.write(data)
        except BaseException:
            f.close()
            tmp.unlink(missing_ok=True)
            raise
    try:
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def write_json(path, value):
    atomic_bytes(path, json.dumps(value, ensure_ascii=False).encode('utf-8'))


def read_json(path, fallback):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return fallback


class Blob(ctypes.Structure):
    _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_ubyte))]


def protected(data, encrypt):
    api = ctypes.WinDLL('crypt32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    free = kernel.LocalFree
    free.argtypes = [ctypes.c_void_p]
    free.restype = ctypes.c_void_p
    pointer = ctypes.POINTER(Blob)
    fn = api.CryptProtectData if encrypt else api.CryptUnprotectData
    fn.argtypes = [pointer, ctypes.c_void_p, pointer, ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, pointer]
    fn.restype = wintypes.BOOL
    buf = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
    src, dst = Blob(len(data), buf), Blob()
    try:
        if not fn(ctypes.byref(src), None, None, None, None, 1, ctypes.byref(dst)):
            raise ctypes.WinError(ctypes.get_last_error())
        return ctypes.string_at(dst.data, dst.size)
    finally:
        ctypes.memset(buf, 0, len(buf))
        if dst.data:
            ctypes.memset(dst.data, 0, dst.size)
            free(dst.data)


def save_login(path, fields):
    atomic_bytes(path, protected(json.dumps(fields).encode(), True))


def load_login(path):
    if not path.exists():
        return {}
    return json.loads(protected(path.read_bytes(), False).decode())


def playable_mp4(path):
    """Require complete top-level boxes, a movie index and nonempty media data."""
    try:
        size = path.stat().st_size
        found = set()
        with path.open('rb') as f:
            pos = 0
            while pos < size:
                head = f.read(8)
                if len(head) != 8:
                    return False
                count, kind = struct.unpack('>I4s', head)
                header = 8
                if count == 1:
                    raw = f.read(8)
                    if len(raw) != 8:
                        return False
                    count, header = struct.unpack('>Q', raw)[0], 16
                elif count == 0:
                    count = size - pos
                if count < header or pos + count > size:
                    return False
                if count > header:
                    found.add(kind)
                pos += count
                f.seek(pos)
        return {b'moov', b'mdat'} <= found
    except OSError:
        return False


def make_job(session, destination, working, drive_folder=None, day=None):
    tag = uuid.uuid4().hex
    (session/'clips').mkdir(parents=True, exist_ok=True)
    job = session/(tag+'.json')
    data={'destination': str(destination) if destination else '', 'drive_folder': drive_folder, 'finished': False}
    if day is not None:data.update(policy='daily-v1',day=day.isoformat())
    write_json(job,data)
    atomic_bytes(working/'record.tag', tag.encode())
    return job


def finish_job(job):
    data = read_json(job, {})
    if 'destination' in data:
        data['finished'] = True
        write_json(job, data)


def recover_finalized(job):
    # The foreground process owns the current session. Only examine abandoned
    # sessions after the worker has had time to close its final segment.
    data = read_json(job, {})
    if data.get('finished') or 'destination' not in data:
        return
    if data.get('policy')=='daily-v1':
        from daily_recording import media
        sources=media(job)
    else:
        sources = list((job.parent/'clips').glob(job.stem+'-*.mp4'))
    if sources and all(playable_mp4(source) for source in sources):
        finish_job(job)


def deliver(job, drive_sender=None):
    data = read_json(job, {})
    if not data.get('finished'):
        return None
    sources = sorted((job.parent/'clips').glob(job.stem+'-*.mp4'))
    if not sources or not all(playable_mp4(p) for p in sources):
        return None
    target = data.get('destination')
    if data.get('drive_folder'):
        if drive_sender is None:raise OSError('Envio ao Drive indisponível.')
        drive_sender(job,data,sources)
    elif target:
        dest = Path(target)
        if not dest.is_dir():
            raise OSError('Pasta sincronizada indisponível.')
        for source in sources:
            final = dest/('Vigia-'+source.name)
            tmp = dest/('.'+final.name+'.partial')
            try:
                shutil.copyfile(source, tmp)
                os.replace(tmp, final)
            finally:
                tmp.unlink(missing_ok=True)
    job.unlink(missing_ok=True)
    return len(sources)
