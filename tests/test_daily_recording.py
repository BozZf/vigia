import datetime as dt
import hashlib
import json
from pathlib import Path
import shutil
import struct
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import daily_recording as daily
import drive_upload as drive
from painel import Panel
import panel_store as store


def box(kind,data):
    return struct.pack('>I4s',8+len(data),kind)+data


class DailyFiles(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name).resolve()
        self.folder=self.root/'nuvem';self.folder.mkdir()
        self.end=dt.date(2027,1,3)
        self.mp4=box(b'ftyp',b'isom')+box(b'mdat',b'video')+box(b'moov',b'index')

    def job(self,day,folder=True,drive_id=None):
        session=self.root/'gravacoes'/day.isoformat()
        j=store.make_job(session,self.folder if folder else None,self.root,drive_id,day=day)
        p=session/'clips'/f'{day}_00-00-00-000_lente-0_{j.stem}.mp4'
        p.write_bytes(self.mp4);store.finish_job(j)
        return j,p

    def test_eight_midnights_leave_exactly_seven_dates_and_other_files(self):
        entries=[]
        other=self.folder/'outra-gravacao.mp4';other.write_bytes(self.mp4)
        for delta in range(7,-1,-1):
            day=self.end-dt.timedelta(days=delta)
            job,path=self.job(day)
            self.assertEqual(daily.maintain(job,day),'delivered')
            entries.append((job,path))
        for job,path in entries:daily.maintain(job,self.end)
        self.assertFalse(entries[0][0].exists());self.assertFalse(entries[0][1].exists())
        for job,path in entries[1:]:
            self.assertTrue(job.exists() and path.exists() and (self.folder/path.name).exists())
        self.assertEqual(len(list(self.folder.glob('*.mp4'))),8)
        self.assertTrue(other.exists())

    def test_legacy_jobs_untouched_by_retention(self):
        old=self.end-dt.timedelta(days=20)
        job=store.make_job(self.root/'old',self.folder,self.root)
        p=job.parent/'clips'/(job.stem+'-lente-0.mp4');p.write_bytes(self.mp4)
        self.assertIsNone(daily.maintain(job,old))
        self.assertTrue(job.exists() and p.exists())

    def test_changed_copy_preserved(self):
        job,source=self.job(self.end)
        daily.maintain(job,self.end)
        dest=self.folder/source.name;dest.write_bytes(b'arquivo do usuario')
        daily.maintain(job,self.end+dt.timedelta(days=7))
        self.assertEqual(dest.read_bytes(),b'arquivo do usuario')
        self.assertFalse(source.exists())

    def test_receipt_survives_destination_offline(self):
        job,source=self.job(self.end)
        daily.maintain(job,self.end)
        offline=self.root/'desmontado';self.folder.rename(offline)
        with self.assertRaises(OSError):daily.maintain(job,self.end+dt.timedelta(days=7))
        self.assertTrue(job.exists());self.assertFalse(source.exists())
        offline.rename(self.folder)
        daily.maintain(job,self.end+dt.timedelta(days=7))
        self.assertFalse((self.folder/source.name).exists());self.assertFalse(job.exists())

    def test_unfinished_mp4_never_published(self):
        job,source=self.job(self.end);source.write_bytes(box(b'mdat',b'partial'))
        self.assertIsNone(daily.maintain(job,self.end))
        self.assertFalse((self.folder/source.name).exists())
        self.assertEqual(daily.maintain(job,self.end+dt.timedelta(days=7)),'expired')

    def test_each_lens_including_negative_index(self):
        job,source=self.job(self.end)
        other=source.with_name(source.name.replace('lente-0','lente--1'));shutil.copyfile(source,other)
        self.assertEqual(daily.maintain(job,self.end),'delivered')
        self.assertEqual(len(list(self.folder.iterdir())),2)

    def test_existing_unowned_destination_is_not_overwritten_or_deleted(self):
        job,source=self.job(self.end)
        dest=self.folder/source.name;dest.write_bytes(b'keep')
        with self.assertRaises(OSError):daily.maintain(job,self.end)
        daily.maintain(job,self.end+dt.timedelta(days=7))
        self.assertEqual(dest.read_bytes(),b'keep')


class Controller(unittest.TestCase):
    def ui(self):
        ui=object.__new__(Panel)
        ui.want_record=True;ui.stopping=False;ui.job=Mock();ui.record_day=dt.date(2026,12,31)
        ui.connected=True;ui.leaving=False;ui.lost_since=0;ui.retry_due=0;ui.record_retry_at=0
        ui.proc=Mock();ui.record_stop=Mock();ui.terminating=False;ui.send=Mock(return_value=True)
        ui.status=Mock();ui.worker_hwnd=123
        return ui

    def test_rotate_once_at_local_midnight(self):
        ui=self.ui()
        ui.recording_tick(ui.record_day,86401);ui.send.assert_not_called()
        ui.recording_tick(dt.date(2027,1,1),86402)
        ui.recording_tick(dt.date(2027,1,1),86403)
        ui.send.assert_called_once_with(12);self.assertTrue(ui.want_record)

    def test_manual_stop_cancels_restart(self):
        ui=self.ui();ui.controls=Mock();ui.toggle_record()
        self.assertFalse(ui.want_record)
        ui.job=None;ui.record_retry_at=1;ui.begin_clip=Mock()
        ui.recording_tick(dt.date.today(),100)
        ui.begin_clip.assert_not_called()

    def test_signal_recovery_resumes_manually_started_recording(self):
        ui=self.ui();ui.connecting=False;ui.stats={'events':[]};ui.connection=Mock();ui.controls=Mock();ui.begin_clip=Mock()
        ui.native({'stage':'video_state','code':4})
        self.assertTrue(ui.want_record);ui.send.assert_called_once_with(12)
        ui.job=None
        ui.native({'stage':'video_state','code':5})
        ui.begin_clip.assert_called_once()

    def test_lost_video_reopens_worker(self):
        ui=self.ui();ui.lost_since=5;ui.connected=False;ui.job=None
        ui.recording_tick(dt.date.today(),51)
        ui.send.assert_called_once_with(11)


class DailyDrive(unittest.TestCase):
    def test_trashed_only_if_parent_markers_and_checksum_match(self):
        job=Path('1'*32+'.json')
        data={'drive_folder':'target','day':'2026-11-01','drive_ids':{k:k for k in ('ok','moved','edited','foreign','gone')},'drive_md5':{'ok':'abc','edited':'abc'}}
        changes=[]
        def call(url,method='GET',*args,**kwargs):
            name=url.split('/files/')[1].split('?')[0]
            if method=='PATCH':
                self.assertEqual(json.loads(args[0]),{'trashed':True})
                changes.append(name);return 200,{},b'{}'
            if name=='gone':return 404,{},b'{}'
            meta={'parents':['else' if name=='moved' else 'target'],'appProperties':{} if name=='foreign' else drive.marker(job,data),
                  'md5Checksum':'changed' if name=='edited' else 'abc','trashed':False}
            return 200,{},json.dumps(meta).encode()
        with patch.object(drive,'LinkedDrive') as client:
            client.return_value.call.side_effect=call
            drive.trash_expired(job,data,Path('drive.dat'))
        self.assertEqual(changes,['ok'])

    def test_resume_confirmed_offset_after_interruption(self):
        with tempfile.TemporaryDirectory() as t:
            folder=Path(t);job=folder/('d'*32+'.json');source=folder/'record.mp4';source.write_bytes(b'abcdef')
            secret=folder/'drive.dat';secret.touch();session='https://www.googleapis.com/upload/session'
            data={'policy':'daily-v1','day':dt.date.today().isoformat(),'drive_folder':'F','drive_ids':{}}
            remote=bytearray();created=False;starts=0;probes=0
            def call(url,method='GET',blob=None,headers=None,allowed=()):
                nonlocal created,starts,probes
                if 'generateIds' in url:return 200,{},b'{"ids":["R"]}'
                if method=='POST':
                    starts+=1;self.assertEqual(json.loads(blob)['appProperties'],drive.marker(job,data))
                    return 200,{'Location':session},b''
                if method=='PUT' and blob==b'':
                    probes+=1;return 308,{'Range':'bytes=0-2'},b''
                if method=='PUT':
                    if len(remote)==3 and not probes:raise OSError('offline')
                    remote.extend(blob)
                    if len(remote)==6:created=True;return 200,{},b'{}'
                    return 308,{'Range':'bytes=0-2'},b''
                if not created:return 404,{},b'{}'
                meta={'parents':['F'],'appProperties':drive.marker(job,data),'size':'6','md5Checksum':hashlib.md5(remote).hexdigest()}
                return 200,{},json.dumps(meta).encode()
            with patch.object(drive,'LinkedDrive') as client,patch.object(store,'save_login',side_effect=store.write_json),patch.object(store,'load_login',side_effect=lambda p:store.read_json(p,{})),patch.object(drive,'CHUNK',3):
                client.return_value.call.side_effect=call
                with self.assertRaises(OSError):drive.upload(job,data,[source],secret)
                drive.upload(job,store.read_json(job,{}),[source],secret)
            self.assertEqual((starts,probes,bytes(remote)),(1,1,b'abcdef'))
            self.assertFalse(list(folder.glob('*.resume')))
