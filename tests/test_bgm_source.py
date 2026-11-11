import hashlib
import io
import json
import tempfile
import threading
import unittest
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


class DownloadTests(unittest.TestCase):
    def setUp(self):
        self.audio=b'valid selected audio'*5000
        payload=io.BytesIO()
        with zipfile.ZipFile(payload,'w',zipfile.ZIP_STORED) as archive:
            archive.writestr('NJAU-CEA-Music-Pack-v1.0.0/assets/audio/music/song.mp3',self.audio)
            archive.writestr('NJAU-CEA-Music-Pack-v1.0.0/assets/audio/music/unused.mp3',b'x'*2_000_000)
        self.archive=payload.getvalue();self.ranges=True;self.bytes_sent=0;self.requests=[]
        owner=self
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                owner.requests.append(self.path)
                content=owner.audio if self.path.startswith('/tracks/') else owner.archive
                interval=self.headers.get('Range')
                if owner.ranges and interval:
                    a,b=map(int,interval.removeprefix('bytes=').split('-'))
                    selected=content[a:b+1]
                    self.send_response(206)
                    self.send_header('Content-Range',f'bytes {a}-{b}/{len(content)}')
                else:
                    selected=content;self.send_response(200)
                self.send_header('Content-Length',str(len(selected)));self.end_headers()
                try:self.wfile.write(selected)
                except (BrokenPipeError,ConnectionResetError,ConnectionAbortedError):pass
                owner.bytes_sent+=len(selected)
            def log_message(self,*args):pass
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        self.worker=threading.Thread(target=self.server.serve_forever,daemon=True);self.worker.start()
        self.url=f'http://127.0.0.1:{self.server.server_port}/pack.zip'
        self.track=dict(id='song',title='Song',path='song.mp3',bytes=len(self.audio),sha256=hashlib.sha256(self.audio).hexdigest())
        self.source=dict(archive_url=self.url,archive_sha256=hashlib.sha256(self.archive).hexdigest())

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.worker.join()

    def download(self,directory,track=None,**extra):
        from pipeline.bgm_source import download_track
        return download_track(track or self.track,self.source,Path(directory),allow_local_http=True,**extra)

    def test_range_download_only_extracts_selected_track(self):
        with tempfile.TemporaryDirectory() as temp:
            target,receipt=self.download(temp)
            self.assertEqual(target.read_bytes(),self.audio)
            self.assertEqual(receipt['mode'],'range_zip')
            self.assertLess(self.bytes_sent,len(self.archive)//2)
            self.assertEqual(len(list(Path(temp).iterdir())),1)

    def test_repository_catalog_binds_files_to_an_immutable_commit(self):
        from unittest.mock import patch
        from pipeline.bgm_source import refresh_catalog
        channel=dict(version='1.3.0',tracks=[self.track],repository_files={'ref':'a'*40})
        with patch('pipeline.bgm_source._read',return_value=json.dumps(channel).encode()) as read:
            result=refresh_catalog({})
        self.assertEqual(result['download']['track_base_url'],
                         f'https://raw.githubusercontent.com/lx-1203/NAU-CEA-News/{"a"*40}/assets/audio/music')
        self.assertEqual(read.call_count,1)

    def test_downloads_only_the_selected_repository_file(self):
        from pipeline.bgm_source import download_track
        source={'track_base_url':self.url.rsplit('/',1)[0]+'/tracks'}
        track=dict(self.track,path='校园 新闻.mp3')
        with tempfile.TemporaryDirectory() as temp:
            target,receipt=download_track(track,source,temp,allow_local_http=True)
            self.assertEqual(target.read_bytes(),self.audio)
            self.assertEqual(receipt['mode'],'repository_file')
            self.assertEqual(self.requests,['/tracks/%E6%A0%A1%E5%9B%AD%20%E6%96%B0%E9%97%BB.mp3'])

    def test_clone_uses_verified_local_track_and_rejects_a_modified_copy(self):
        from pipeline.bgm_source import download_track
        source={'track_base_url':self.url.rsplit('/',1)[0]+'/tracks'}
        with tempfile.TemporaryDirectory() as temp:
            library=Path(temp)/'library'
            library.mkdir()
            song=library/self.track['path']
            song.write_bytes(self.audio)
            target,receipt=download_track(self.track,source,Path(temp)/'first',local_music_directory=library,
                                          allow_local_http=True)
            self.assertEqual(target.read_bytes(),self.audio)
            self.assertEqual(receipt['download_bytes'],0)
            song.write_bytes(b'changed')
            with self.assertRaises(ValueError):
                download_track(self.track,source,Path(temp)/'second',local_music_directory=library,allow_local_http=True)
            self.assertFalse(self.requests)
            self.assertEqual(list((Path(temp)/'second').iterdir()),[])

    def test_reusing_historical_track_records_the_actual_repository_source(self):
        from unittest.mock import patch
        from pipeline.bgm import BgmSession,Rotation
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            library=root/'assets/audio/music';library.mkdir(parents=True)
            (library/self.track['path']).write_bytes(self.audio)
            output=root/'result.mp4';output.write_bytes(b'verified test video')
            day='2026-11-11'
            old=Rotation(root/'data/music',dict(version='1.2.0',tracks=[self.track],download=self.source))
            old.reserve(day)
            old.commit(day,'a'*64)
            new=dict(version='1.3.0',tracks=[self.track],
                     download={'track_base_url':'https://raw.githubusercontent.com/example/repo/'+'a'*40+'/assets/audio/music'})
            with patch.dict('os.environ',{'NJAU_CEA_DATA_ROOT':str(root/'data')}), \
                    patch('pipeline.bgm_source.refresh_catalog',return_value=new),patch('pipeline.bgm._ffmpeg'):
                with BgmSession(root,day) as session:
                    result=session.commit(output)
            self.assertEqual(result['selection']['catalog_version'],'1.2.0')
            self.assertEqual(result['audio_source']['catalog_version'],'1.3.0')
            self.assertEqual(result['download']['mode'],'local_repository_file')
            self.assertEqual(old.status()['assignments'][day]['catalog_version'],'1.2.0')

    def test_no_range_uses_temporary_archive_and_keeps_no_zip(self):
        self.ranges=False
        with tempfile.TemporaryDirectory() as temp:
            target,receipt=self.download(temp)
            self.assertEqual(target.read_bytes(),self.audio)
            self.assertEqual(receipt['mode'],'temporary_zip')
            self.assertEqual(list(Path(temp).glob('*.zip')),[])

    def test_checksum_mismatch_removes_download_and_partial_files(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(ValueError):self.download(temp,dict(self.track,sha256='0'*64))
            self.assertEqual(list(Path(temp).iterdir()),[])

    def test_archive_budget_is_enforced_before_download(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(ValueError):self.download(temp,max_archive_bytes=100)
            self.assertEqual(list(Path(temp).iterdir()),[])

    def test_archive_full_download_checksum_is_verified(self):
        self.ranges=False;self.source['archive_sha256']='0'*64
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(ValueError):self.download(temp)
            self.assertEqual(list(Path(temp).iterdir()),[])

    def test_malformed_track_path_and_public_http_are_rejected(self):
        from pipeline.bgm_source import validate_catalog,check_url
        for path in ['../escape.mp3','C:/escape.mp3','a\\b.mp3','CON.mp3','song.mp3:ads']:
            with self.assertRaises(ValueError):validate_catalog(dict(version='1.0.0',tracks=[dict(self.track,path=path)]))
        with self.assertRaises(ValueError):check_url('http://example.com/pack.zip')

    def test_identical_hash_cannot_have_conflicting_byte_size(self):
        from pipeline.bgm_source import validate_catalog
        with self.assertRaises(ValueError):validate_catalog(dict(version='1.0.0',tracks=[self.track,dict(self.track,id='other',path='other.mp3',bytes=99)]))

    def test_channel_ahead_of_draft_uses_latest_published_release(self):
        from unittest.mock import patch
        from urllib.error import HTTPError
        from pipeline.bgm_source import refresh_catalog
        old=dict(version='1.0.0',tracks=[self.track])
        channel=dict(old,version='1.1.0')
        feed=b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><link href="https://github.com/lx-1203/NAU-CEA-News/releases/tag/music-pack-v1.0.0"/></entry></feed>'
        def read(url,*args):
            if '/main/' in url:return json.dumps(channel).encode()
            if 'music-pack-v1.1.0/' in url:raise HTTPError(url,404,'draft',{},None)
            if url.endswith('.atom'):return feed
            if url.endswith('MUSIC_MANIFEST.json'):return json.dumps(old).encode()
            return (hashlib.sha256(self.archive).hexdigest()+'  NJAU-CEA-Music-Pack-v1.0.0.zip\n').encode()
        with patch('pipeline.bgm_source._read',side_effect=read):
            catalog=refresh_catalog({})
        self.assertEqual(catalog['version'],'1.0.0')
        self.assertEqual(catalog['channel_version'],'1.1.0')

if __name__=='__main__':unittest.main()
