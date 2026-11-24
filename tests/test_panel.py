from pathlib import Path
import hashlib
import json
import os
import struct
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import drive_upload as drive
import panel_store as store
from painel import Panel


def box(kind,data):
    return struct.pack('>I4s',8+len(data),kind)+data


class Clips(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name)
        self.dest=self.root/'drive';self.dest.mkdir()
        self.session=self.root/'session'
        self.job=store.make_job(self.session,self.dest,self.root)
        self.source=self.session/'clips'/(self.job.stem+'-lente-0.mp4')
        self.media=box(b'ftyp',b'isom')+box(b'mdat',b'PCM')+box(b'moov',b'index')

    def test_wait_until_finalized_and_index_written(self):
        self.source.write_bytes(self.media)
        self.assertIsNone(store.deliver(self.job))
        store.finish_job(self.job)
        self.source.write_bytes(self.media[:-2])
        self.assertIsNone(store.deliver(self.job))
        self.assertEqual(list(self.dest.iterdir()),[])
        self.source.write_bytes(self.media)
        self.assertEqual(store.deliver(self.job),1)
        self.assertFalse(self.job.exists())
        self.assertEqual(next(self.dest.iterdir()).read_bytes(),self.media)
        self.assertEqual(self.source.read_bytes(),self.media)

    def test_disconnected_destination_retries_same_file(self):
        store.finish_job(self.job);self.source.write_bytes(self.media);self.dest.rmdir()
        with self.assertRaises(OSError):store.deliver(self.job)
        self.assertTrue(self.job.is_file())
        self.dest.mkdir()
        self.assertEqual(store.deliver(self.job),1)

    def test_partial_copy_cannot_replace_completed_clip(self):
        store.finish_job(self.job);self.source.write_bytes(self.media)
        final=self.dest/('Vigia-'+self.source.name);final.write_bytes(b'previous')
        with patch.object(store.shutil,'copyfile',side_effect=OSError):
            with self.assertRaises(OSError):store.deliver(self.job)
        self.assertEqual(list(self.dest.iterdir()),[final])
        self.assertEqual(final.read_bytes(),b'previous')
        self.assertTrue(self.job.exists())

    def test_direct_upload_requires_matching_link(self):
        data={'drive_folder':'original'}
        with patch.object(store,'load_login',return_value={'folder':'other'}), patch.object(drive,'request') as http:
            with self.assertRaises(drive.DriveError):drive.upload(self.job,data,[self.source],self.root/'drive.dat')
            http.assert_not_called()

    def test_direct_upload_resumes_blocks_and_checks_checksum(self):
        self.source.write_bytes(self.media)
        secret=self.root/'drive.dat';secret.touch()
        conf={'folder':'folder','client_id':'a','client_secret':'b','refresh_token':'refresh'}
        data={'finished':True,'drive_folder':'folder'};store.write_json(self.job,data)
        calls=[];received=bytearray();created=False
        def http(url,method='GET',data=None,headers=None,allowed=()):
            nonlocal created
            calls.append((method,url))
            if 'generateIds' in url:return 200,{},b'{"ids":["remote"]}'
            if method=='POST':
                self.assertEqual(json.loads(data)['id'],'remote')
                return 200,{'Location':'https://www.googleapis.com/upload/session'},b''
            if method=='PUT':
                self.assertTrue(headers['Content-Range'].startswith(f'bytes {len(received)}-'))
                received.extend(data)
                if len(received)<len(self.media):return 308,{'Range':f'bytes=0-{len(received)-1}'},b''
                created=True;return 201,{},b'{}'
            if not created:return 404,{},b'{}'
            return 200,{},json.dumps({'size':str(len(received)),'md5Checksum':hashlib.md5(received).hexdigest()}).encode()
        with patch.object(store,'load_login',return_value=conf),patch.object(drive,'token_request',return_value={'access_token':'access'}),patch.object(drive,'request',side_effect=http),patch.object(drive,'CHUNK',11):
            drive.upload(self.job,data,[self.source],secret)
            self.assertEqual(received,self.media)
            self.assertEqual(store.read_json(self.job,{})['drive_ids'][self.source.name],'remote')
            calls.clear()
            drive.upload(self.job,data,[self.source],secret)
            self.assertEqual([m for m,_ in calls],['GET'])

    def test_recover_only_finalized_media_in_an_abandoned_session(self):
        self.source.write_bytes(self.media[:-1]);store.recover_finalized(self.job)
        self.assertFalse(store.read_json(self.job,{})['finished'])
        self.source.write_bytes(self.media);store.recover_finalized(self.job)
        self.assertTrue(store.read_json(self.job,{})['finished'])

    def test_local_only_does_not_send(self):
        self.job=store.make_job(self.session,'',self.root)
        source=self.session/'clips'/(self.job.stem+'-lente-1.mp4');source.write_bytes(self.media)
        store.finish_job(self.job)
        upload=Mock();self.assertEqual(store.deliver(self.job,upload),1)
        upload.assert_not_called()
        self.assertTrue(source.exists())


class Controls(unittest.TestCase):
    def test_alarm_second_click_stops_without_picking_a_file(self):
        ui=object.__new__(Panel);ui.alert=True;ui.send=Mock()
        ui.toggle_alert()
        ui.send.assert_called_once_with(9)

    def test_recorder_stop_is_not_a_toggle(self):
        ui=object.__new__(Panel);ui.send=Mock(return_value=True)
        ui.stop_clip();ui.send.assert_called_once_with(12)
        self.assertTrue(ui.stopping)

    def test_light_only_highlights_on_device_reply(self):
        ui=object.__new__(Panel);ui.light=False;ui.status=Mock();ui.stats={'events':[]};ui.controls=Mock();ui.alert=False
        ui.native({'stage':'light_payload','hex':b'{"type":11,"errCode":1}'.hex()})
        ui.native({'stage':'light_state','code':1})
        self.assertFalse(ui.light)
        ui.native({'stage':'light_payload','hex':b'{"type":11,"errCode":0}'.hex()})
        ui.native({'stage':'light_state','code':1})
        self.assertTrue(ui.light)

    def test_drive_session_rejects_unexpected_hosts(self):
        self.assertFalse(drive.valid_session('https://elsewhere.invalid/session'))
        self.assertFalse(drive.valid_session('http://www.googleapis.com/upload'))
        self.assertTrue(drive.valid_session('https://www.googleapis.com/upload/session'))

    @unittest.skipUnless(os.name=='nt','DPAPI requires a Windows user account')
    def test_login_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'login.dat';data={'password':'not-cleartext','account':'sample'}
            store.save_login(path,data)
            self.assertNotIn(b'not-cleartext',path.read_bytes())
            self.assertEqual(store.load_login(path),data)
