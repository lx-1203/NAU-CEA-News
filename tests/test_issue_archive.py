import json, tempfile, unittest, shutil
from pathlib import Path
from unittest.mock import patch
from pipeline.issue_archive import export_issue, verify_issue, publish_current


class IssueArchiveTests(unittest.TestCase):
    def test_relocated_issue_uses_relative_references_and_preserves_video(self):
        with tempfile.TemporaryDirectory(prefix='归档 空格 ') as temp:
            root=Path(temp);old=root/'old';old.mkdir();(old/'media.jpg').write_bytes(b'original-photo')
            (old/'news.mp4').write_bytes(b'unchanged-master')
            (old/'watch.html').write_text('<video src="news.mp4"></video>',encoding='utf8')
            (old/'daily.html').write_text('<img src="media.jpg"><a href="watch.html">播放</a>',encoding='utf8')
            edition={'date':'2026-11-10','stories':[{'media':[{'path':str(old/'media.jpg')}]}]}
            (old/'edition.json').write_text(json.dumps(edition),encoding='utf8')
            pointer=dict(date='2026-11-10',video=str(old/'news.mp4'),player=str(old/'watch.html'),report=str(old/'daily.html'),edition=str(old/'edition.json'),run_dir=str(old))
            result=export_issue(pointer,root/'portable')
            verify_issue(root/'portable')
            self.assertEqual((root/'portable/deliverables/current/news.mp4').read_bytes(),b'unchanged-master')
            self.assertNotIn(str(old),(root/'portable/deliverables/current/daily.html').read_text('utf8'))
            self.assertTrue((root/'portable/media/images/media.jpg').is_file())
            self.assertEqual(result['date'],'2026-11-10')
            with self.assertRaises(FileExistsError):export_issue(pointer,root/'portable')
            moved=root/'另一台电脑 有空格'/'本期';moved.parent.mkdir()
            shutil.move(str(root/'portable'),str(moved));shutil.rmtree(old)
            verify_issue(moved)

    def test_missing_reference_fails_instead_of_silently_shipping_broken_page(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'news.mp4').write_bytes(b'video')
            (root/'watch.html').write_text('<video src="news.mp4"></video>')
            (root/'daily.html').write_text('<img src="missing.jpg">')
            (root/'edition.json').write_text(json.dumps({'date':'2026-11-09','stories':[]}))
            pointer=dict(date='2026-11-09',video=str(root/'news.mp4'),player=str(root/'watch.html'),report=str(root/'daily.html'),edition=str(root/'edition.json'),run_dir=str(root))
            with self.assertRaises(FileNotFoundError):export_issue(pointer,root/'out')
            self.assertFalse((root/'out').exists())

    def fixture(self, root):
        (root/'news.mp4').write_bytes(b'original-video')
        (root/'watch.html').write_text('<video src=news.mp4></video>',encoding='utf8')
        (root/'daily.html').write_text('<a href="watch.html">play</a>',encoding='utf8')
        (root/'edition.json').write_text(json.dumps(dict(date='2026-11-10',stories=[])),encoding='utf8')
        return dict(date='2026-11-10',video=str(root/'news.mp4'),player=str(root/'watch.html'),report=str(root/'daily.html'),run_dir=str(root))

    def test_evidence_audio_and_historical_manifests_survive_relocation(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source=root/'source';source.mkdir();pointer=self.fixture(source)
            evidence=source/'date.txt';evidence.write_text('original date proof',encoding='utf8')
            edition=dict(date='2026-11-10',stories=[dict(date_evidence=dict(path=str(evidence)))])
            original=json.dumps(edition).encode();(source/'edition.json').write_bytes(original)
            manifest=b'{"original_absolute_path":"C:/old/immutable"}'
            (source/'manifest.json').write_bytes(manifest)
            pointer['manifest']=str(source/'manifest.json')
            (source/'cue-000.wav').write_bytes(b'final-cue')
            (source/'narration.wav').write_bytes(b'combined')
            audio={'0':dict(path=str(source/'cue-000.wav'),text='speech',voice='approved')}
            (source/'audio-manifest.json').write_text(json.dumps(audio),encoding='utf8')
            (source/'chapters.json').write_text('{"chapters":[]}',encoding='utf8')
            (source/'chapters.vtt').write_text('WEBVTT\n',encoding='utf8')
            pointer['chapters']=str(source/'chapters.json')
            result=export_issue(pointer,root/'archive')
            archive=root/'archive'
            self.assertEqual((archive/'review/immutable-originals/edition.json').read_bytes(),original)
            self.assertEqual((archive/'review/immutable-originals/manifest.json').read_bytes(),manifest)
            portable=json.loads((archive/'editorial/edition.json').read_text('utf8'))
            self.assertEqual(portable['stories'][0]['date_evidence']['path'],'../media/evidence/date.txt')
            self.assertEqual((archive/'audio/cues/cue-000.wav').read_bytes(),b'final-cue')
            self.assertEqual((archive/'audio/combined-narration.wav').read_bytes(),b'combined')
            self.assertEqual((archive/'deliverables/current/chapters.vtt').read_text('utf8'),'WEBVTT\n')
            self.assertTrue(all(not Path(name).is_absolute() for name in result['files']))
            shutil.rmtree(source)
            verify_issue(archive)

    def test_date_rejection_and_hash_tamper(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source=root/'source';source.mkdir();pointer=self.fixture(source)
            for day in ('../2026-11-10','2026-02-30','2026-11-09'):
                with self.assertRaises(ValueError):export_issue(dict(pointer,date=day),root/'archive')
            export_issue(pointer,root/'archive')
            (root/'archive/deliverables/current/news.mp4').write_bytes(b'tampered-video')
            with self.assertRaisesRegex(ValueError,'hash mismatch'):verify_issue(root/'archive')

    def test_missing_date_evidence_fails_and_source_is_unchanged(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source=root/'source';source.mkdir();pointer=self.fixture(source)
            original=json.dumps(dict(date='2026-11-10',stories=[dict(date_evidence=dict(path='missing.txt'))])).encode()
            (source/'edition.json').write_bytes(original)
            with self.assertRaises(FileNotFoundError):export_issue(pointer,root/'archive')
            self.assertEqual((source/'edition.json').read_bytes(),original)
            self.assertEqual((source/'news.mp4').read_bytes(),b'original-video')

    def test_report_links_to_selected_mixed_master(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source=root/'source';source.mkdir();pointer=self.fixture(source)
            mixed=source/'mix';mixed.mkdir()
            (mixed/'final.mp4').write_bytes(b'approved-final')
            (mixed/'watch.html').write_text('<video src="final.mp4"></video>',encoding='utf8')
            pointer.update(video=str(mixed/'final.mp4'),player=str(mixed/'watch.html'))
            export_issue(pointer,root/'archive')
            self.assertEqual((root/'archive/deliverables/current/news.mp4').read_bytes(),b'approved-final')
            self.assertIn('href="watch.html"',(root/'archive/deliverables/current/daily.html').read_text('utf8'))
            self.assertEqual(len(list((root/'archive').rglob('*.mp4'))),1)

    def test_image_srcset_and_css_dependencies_are_copied(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source=root/'source';source.mkdir();pointer=self.fixture(source)
            (source/'a.jpg').write_bytes(b'image-a');(source/'b.jpg').write_bytes(b'image-b')
            (source/'screen.css').write_text('body{background:url(a.jpg)}',encoding='utf8')
            (source/'daily.html').write_text('<link href="screen.css"><img srcset="a.jpg 1x,b.jpg 2x">',encoding='utf8')
            export_issue(pointer,root/'archive');shutil.rmtree(source)
            verify_issue(root/'archive')
            self.assertTrue((root/'archive/media/images/b.jpg').is_file())

    def test_raw_html_date_evidence_is_hash_checked_without_operational_link_scanning(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source=root/'source';source.mkdir();pointer=self.fixture(source)
            evidence=b'<a href="/feed/">feed</a><script>j.href="t+h._hjSettings.hjid+j+h._hjSettings.hjsv;"</script>'
            (source/'original.html').write_bytes(evidence)
            edition=dict(date='2026-11-10',stories=[dict(date_evidence=dict(path=str(source/'original.html')))])
            (source/'edition.json').write_text(json.dumps(edition),encoding='utf8')
            exported=export_issue(pointer,root/'archive')
            proof=root/'archive/media/evidence/original.html'
            self.assertEqual(proof.read_bytes(),evidence)
            self.assertNotIn('media/evidence/original.html',exported['operational_resources'])
            shutil.rmtree(source)
            verify_issue(root/'archive')
            proof.write_bytes(b'changed evidence')
            with self.assertRaisesRegex(ValueError,'hash mismatch'):verify_issue(root/'archive')

    def test_publish_current_preserves_authoring_and_retains_previous_current(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source=root/'source';source.mkdir();pointer=self.fixture(source)
            (source/'photo.jpg').write_bytes(b'original-photo')
            (source/'daily.html').write_text('<img src="photo.jpg"><a href="watch.html">play</a>',encoding='utf8')
            (source/'source-proof.txt').write_bytes(b'original-proof')
            (source/'cue-000.wav').write_bytes(b'approved-cue')
            (source/'narration.wav').write_bytes(b'first-combined-narration')
            (source/'timeline.json').write_text(json.dumps({'shots':[dict(audio='cue-000.wav')]}),encoding='utf8')
            (source/'audio-manifest.json').write_text(json.dumps({'0':dict(path=str(source/'cue-000.wav'))}),encoding='utf8')
            edition=dict(date='2026-11-10',stories=[dict(media=[dict(path=str(source/'photo.jpg'))],
                         date_evidence=dict(path=str(source/'source-proof.txt')))])
            (source/'edition.json').write_text(json.dumps(edition),encoding='utf8')
            issue=root/'issue'
            original_files={'editorial/edition.json':b'{"date":"2026-11-10","draft":true}',
                            'editorial/candidates.json':b'candidate originals',
                            'tasks/status.json':b'authoring task state',
                            'media/evidence/editor-proof.txt':b'authoring proof'}
            for name,content in original_files.items():
                path=issue/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(content)
            first=publish_current(pointer,issue)
            verify_issue(issue,first['ledger'])
            portable=json.loads((issue/'deliverables/current/edition.json').read_text('utf8'))
            self.assertTrue(portable['stories'][0]['media'][0]['path'].startswith('../../media/images/'))
            self.assertEqual((issue/'deliverables/current'/portable['stories'][0]['media'][0]['path']).read_bytes(),b'original-photo')
            self.assertFalse((issue/'ISSUE_MANIFEST.json').exists())
            (source/'news.mp4').write_bytes(b'reviewed-second-master')
            (source/'cue-000.wav').write_bytes(b'revised-cue')
            (source/'narration.wav').write_bytes(b'revised-combined-narration')
            second=publish_current(pointer,issue)
            verify_issue(issue,second['ledger'])
            self.assertEqual((issue/'deliverables/current/news.mp4').read_bytes(),b'reviewed-second-master')
            self.assertEqual((issue/second['previous_current']/'news.mp4').read_bytes(),b'original-video')
            first_audio=json.loads((issue/second['previous_current']/'audio-manifest.json').read_text('utf8'))
            second_audio=json.loads((issue/'deliverables/current/audio-manifest.json').read_text('utf8'))
            self.assertEqual((issue/second['previous_current']/first_audio['0']['path']).read_bytes(),b'approved-cue')
            self.assertEqual((issue/'deliverables/current'/second_audio['0']['path']).read_bytes(),b'revised-cue')
            first_combined=next(name for name in first['files'] if name.endswith('/combined-narration.wav'))
            second_combined=next(name for name in second['files'] if name.endswith('/combined-narration.wav'))
            self.assertEqual((issue/first_combined).read_bytes(),b'first-combined-narration')
            self.assertEqual((issue/second_combined).read_bytes(),b'revised-combined-narration')
            for folder,expected in [(issue/second['previous_current'],b'approved-cue'),(issue/'deliverables/current',b'revised-cue')]:
                timeline=json.loads((folder/'timeline.json').read_text('utf8'))
                self.assertEqual((folder/timeline['shots'][0]['audio']).read_bytes(),expected)
            for name,content in original_files.items():self.assertEqual((issue/name).read_bytes(),content)
            moved=root/'另一个目录 有空格';shutil.move(str(issue),str(moved));shutil.rmtree(source)
            verify_issue(moved,second['ledger'])

    def test_publish_current_namespaces_media_without_overwriting_authoring_original(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source=root/'source';source.mkdir();pointer=self.fixture(source)
            (source/'photo.jpg').write_bytes(b'new-photo')
            (source/'daily.html').write_text('<img src="photo.jpg">',encoding='utf8')
            issue=root/'issue';(issue/'media/images').mkdir(parents=True)
            (issue/'media/images/photo.jpg').write_bytes(b'existing-original')
            (issue/'deliverables/current').mkdir(parents=True)
            (issue/'deliverables/current/news.mp4').write_bytes(b'previous-final')
            result=publish_current(pointer,issue)
            verify_issue(issue,result['ledger'])
            self.assertEqual((issue/'media/images/photo.jpg').read_bytes(),b'existing-original')
            self.assertEqual((issue/result['previous_current']/'news.mp4').read_bytes(),b'previous-final')

    def test_publish_current_failed_final_check_restores_previous_current(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source=root/'source';source.mkdir();pointer=self.fixture(source)
            issue=root/'issue';first=publish_current(pointer,issue)
            (source/'news.mp4').write_bytes(b'new-reviewed-master')
            def reject_installed(target, finalization_ledger=None):
                if finalization_ledger is not None:raise ValueError('simulated final check failure')
                return verify_issue(target)
            with patch('pipeline.issue_archive.verify_issue',side_effect=reject_installed):
                with self.assertRaisesRegex(ValueError,'simulated final check failure'):publish_current(pointer,issue)
            self.assertEqual((issue/'deliverables/current/news.mp4').read_bytes(),b'original-video')
            verify_issue(issue,first['ledger'])
