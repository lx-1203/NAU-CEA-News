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
        self.archive=payload.getvalue();self.ranges=True;self.bytes_sent=0
        owner=self
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                content=owner.archive
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
