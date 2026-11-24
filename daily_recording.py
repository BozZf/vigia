"""Local calendar rotation and seven-date retention for Vigia's daily recordings."""
import datetime as dt
import os
from pathlib import Path
import re
import shutil
import stat
import tempfile

import panel_store as store


def expired(day, today):
    return dt.date.fromisoformat(day) < today - dt.timedelta(days=6)


def media(job):
    # Each recording has a random 128-bit tag, committed before the SDK starts.
    match = re.compile(r'\d{4}-\d\d-\d\d_\d\d-\d\d-\d\d-\d{3}_lente--?\d+_'+re.escape(job.stem)+r'\.mp4\Z')
    return sorted(p for p in (job.parent/'clips').glob('*_'+job.stem+'.mp4') if match.fullmatch(p.name))


def stamp(path):
    s=path.lstat()
    if not stat.S_ISREG(s.st_mode) or path.is_symlink():
        raise OSError('O arquivo registrado foi substituído.')
    return [s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns]


def remove_registered(path, expected):
    try:
        if stamp(path)==expected:
            path.unlink()
    except FileNotFoundError:
        pass


def managed(job, data):
    if data.get('policy')!='daily-v1' or not re.fullmatch('[0-9a-f]{32}',job.stem):
        return False
    # Neither a linked session nor a linked clips directory is managed.
    for path in (job,job.parent,job.parent/'clips'):
        try:
            info=path.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info,'st_file_attributes',0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
            return False
    return True


def sync_file(job, data, source):
    dest=Path(data['destination'])
    if not dest.is_dir():raise OSError('Pasta de destino indisponível.')
    name=source.name
    final=dest/name
    copies=data.setdefault('copies',{})
    if name in copies:return
    staged=data.setdefault('staged',{})
    if final.exists():
        if name not in staged or stamp(final)!=staged[name]['stamp']:
            raise OSError('Já existe outro arquivo com este nome.')
    else:
        previous=staged.get(name)
        if previous:
            remove_registered(dest/Path(previous['temp']).name,previous['stamp'])
        with tempfile.NamedTemporaryFile(dir=dest,prefix='.'+job.stem+'-',suffix='.partial',delete=False) as handle:
            tmp=Path(handle.name)
        try:
            shutil.copyfile(source,tmp)
            staged[name]={'temp':tmp.name,'stamp':stamp(tmp)}
            store.write_json(job,data)
            if os.name=='nt':
                os.rename(tmp,final)  # Windows fails if final already exists.
            else:
                os.link(tmp,final)
        finally:tmp.unlink(missing_ok=True)
    copies[name]=stamp(final)
    store.write_json(job,data)


def maintain(job, today, sender=None, trash=None):
    data=store.read_json(job,{})
    if not managed(job,data):return None
    if data.get('delivered') and not expired(data['day'],today):return None
    sources=media(job)
    if expired(data['day'],today):
        recorded=data.get('local_files',{})
        for source in sources:
            # An interrupted native recording may have no finalized receipt.
            remove_registered(source,recorded.get(source.name) or stamp(source))
        for path in job.parent.glob(job.stem+'.*.resume'):
            if not path.is_symlink():path.unlink(missing_ok=True)
        if data.get('copies') or data.get('staged'):
            dest=Path(data['destination'])
            if not dest.is_dir():raise OSError('Limpeza pendente até a pasta voltar.')
            for name,entry in data.get('staged',{}).items():
                if name not in recorded or Path(name).name!=name:continue
                remove_registered(dest/name,entry['stamp'])
                remove_registered(dest/Path(entry['temp']).name,entry['stamp'])
            for name,expected in data.get('copies',{}).items():
                if name in recorded and Path(name).name==name:remove_registered(dest/name,expected)
        if data.get('drive_ids'):
            if trash is None:raise OSError('Limpeza do Drive pendente.')
            trash(job,data)
        job.unlink(missing_ok=True)
        return 'expired'
    if data.get('delivered'):return None
    if not data.get('finished') or not sources or not all(store.playable_mp4(p) for p in sources):return None
    if not data.get('local_files'):
        data['local_files']={p.name:stamp(p) for p in sources}
        store.write_json(job,data)
    if {p.name for p in sources}!=set(data['local_files']) or any(stamp(p)!=data['local_files'][p.name] for p in sources):
        raise OSError('Uma gravação mudou antes do envio.')
    if data.get('drive_folder'):
        if sender is None:raise OSError('Drive indisponível.')
        sender(job,data,sources)
    elif data.get('destination'):
        for source in sources:sync_file(job,data,source)
    data['delivered']=True
    store.write_json(job,data)
    return 'delivered'
