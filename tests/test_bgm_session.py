import hashlib
import json
import math
import struct
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

from pipeline.bgm import BgmSession, _ffmpeg


class SessionTests(unittest.TestCase):
    def setup_fixture(self,root):
        (root/'config').mkdir()
        original=root/'user-original.wav'
        with wave.open(str(original),'wb') as stream:
            stream.setparams((1,2,24000,0,'NONE','not compressed'))
            stream.writeframes(b''.join(struct.pack('<h',int(5000*math.sin(i*.1))) for i in range(24000)))
        data=original.read_bytes()
        track=dict(id='test',title='Test tone',path='test.wav',bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
        catalog=dict(version='1.0.0',tracks=[track],download=dict(archive_url='https://example.com/pack.zip',archive_sha256='a'*64))
        def download(track,source,cache):
            target=cache/(track['sha256']+'.wav');target.write_bytes(data)
            return target,dict(mode='test_fixture',download_bytes=len(data))
        return original,catalog,download

    def test_session_failure_does_not_consume_and_always_frees_audio(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);original,catalog,download=self.setup_fixture(root)
            with patch('pipeline.bgm_source.refresh_catalog',return_value=catalog),patch('pipeline.bgm_source.download_track',side_effect=download):
                with self.assertRaisesRegex(RuntimeError,'render failed'):
                    with BgmSession(root,'2026-11-11') as session:
                        self.assertTrue(session.audio.exists())
                        raise RuntimeError('render failed')
            self.assertTrue(original.exists())
            self.assertEqual(list((root/'data/music/cache').glob('*.wav')),[])
            state=json.loads((root/'data/music/history.json').read_text())
            self.assertEqual(state['used'],[])

    def test_real_mix_preserves_video_packets_and_mutes_opening_and_interlude(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);original,catalog,download=self.setup_fixture(root)
            source=root/'source.mp4';target=root/'mixed.mp4'
            _ffmpeg(['-f','lavfi','-i','color=c=blue:s=160x90:r=30:d=4','-f','lavfi','-i',
                     'anullsrc=r=48000:cl=stereo','-t','4','-c:v','libx264','-threads','1','-c:a','aac',source])
            with patch('pipeline.bgm_source.refresh_catalog',return_value=catalog),patch('pipeline.bgm_source.download_track',side_effect=download):
                with BgmSession(root,'2026-11-11') as session:
                    session.mix(source,target,dict(opening=dict(start=0,end=.5),interludes=[dict(start=2,end=3)],
                                                   outro=dict(start=3.5,end=4)))
                    _ffmpeg(['-xerror','-i',target,'-f','null','-'])
                    receipt=session.commit(target)
            self.assertEqual(receipt['status'],'committed')
            self.assertFalse(session.audio.exists());self.assertTrue(original.exists())
            def video_hash(path):return _ffmpeg(['-i',path,'-map','0:v','-c','copy','-f','hash','-hash','sha256','-']).stdout
            self.assertEqual(video_hash(source),video_hash(target))
            pcm=_ffmpeg(['-i',target,'-vn','-ac','1','-ar','24000','-f','s16le','-']).stdout
            def peak(a,b):
                samples=struct.unpack('<'+'h'*((int(b*24000)-int(a*24000))),pcm[int(a*24000)*2:int(b*24000)*2])
                return max(map(abs,samples))
            self.assertLess(peak(.1,.4),10)
            self.assertLess(peak(2.05,2.95),10)
            self.assertLess(peak(3.55,3.95),10)
            self.assertGreater(peak(1.5,1.8),20)
            state=json.loads((root/'data/music/history.json').read_text())
            self.assertEqual(len(state['used']),1)

    def test_render_metadata_failure_leaves_usage_uncommitted(self):
        import pipeline.render as renderer
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);original,catalog,download=self.setup_fixture(root)
            edition=root/'edition.json';edition.write_text('{"date":"2026-11-11"}')
            run=root/'run'
            def fake_render(*args,**kwargs):
                run.mkdir();(run/'bgm-receipt.json').write_text('{"status":"validated"}')
                return dict(files={},bgm={})
            with patch.object(renderer,'ROOT',root),patch.object(renderer,'validate_edition',side_effect=lambda x:x),\
                 patch.object(renderer,'_render_edition',side_effect=fake_render),\
                 patch.object(renderer,'write_json',side_effect=OSError('metadata failed')),\
                 patch('pipeline.bgm_source.refresh_catalog',return_value=catalog),\
                 patch('pipeline.bgm_source.download_track',side_effect=download):
                with self.assertRaisesRegex(OSError,'metadata failed'):
                    renderer.render_edition(edition,run)
            state=json.loads((root/'data/music/history.json').read_text())
            self.assertEqual(state['used'],[])
            self.assertEqual(list((root/'data/music/cache').glob('*.wav')),[])

    def test_mixed_audio_keeps_existing_minus_three_db_true_peak_requirement(self):
        from pipeline.bgm import true_peak
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);original,catalog,download=self.setup_fixture(root)
            source=root/'near-ceiling.mp4';target=root/'safe-mix.mp4'
            _ffmpeg(['-f','lavfi','-i','color=c=blue:s=160x90:r=30:d=4',
                     '-f','lavfi','-i','aevalsrc=0.70*sin(2*PI*1000*t)|0.70*sin(2*PI*1000*t):s=48000:d=4',
                     '-t','4','-c:v','libx264','-threads','1','-c:a','alac',source])
            self.assertLessEqual(true_peak(source),-3)
            with patch('pipeline.bgm_source.refresh_catalog',return_value=catalog),patch('pipeline.bgm_source.download_track',side_effect=download):
                with BgmSession(root,'2026-11-11') as session:
                    session.mix(source,target,{})
                    self.assertLessEqual(true_peak(target),-3)

    def test_render_wrapper_commits_only_after_metadata_and_cache_are_sealed(self):
        import pipeline.render as renderer
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);original,catalog,download=self.setup_fixture(root)
            edition=root/'edition.json';edition.write_text('{"date":"2026-11-11"}')
            run=root/'run';commits=[]
            def fake_render(*args,**kwargs):
                run.mkdir();(run/'bgm-receipt.json').write_text('{"status":"validated"}')
                (run/'news.mp4').write_bytes(b'checked video fixture')
                return dict(files={},bgm={})
            original_commit=BgmSession.commit
            def observed_commit(session,video):
                self.assertTrue((run/'manifest.json').is_file())
                self.assertFalse(session.audio.exists())
                commits.append(True)
                return original_commit(session,video)
            with patch.object(renderer,'ROOT',root),patch.object(renderer,'validate_edition',side_effect=lambda x:x),\
                 patch.object(renderer,'_render_edition',side_effect=fake_render),\
                 patch.object(BgmSession,'commit',observed_commit),\
                 patch('pipeline.bgm_source.refresh_catalog',return_value=catalog),\
                 patch('pipeline.bgm_source.download_track',side_effect=download):
                renderer.render_edition(edition,run)
            self.assertEqual(commits,[True])

if __name__=='__main__':unittest.main()
