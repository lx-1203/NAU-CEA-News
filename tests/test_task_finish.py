import json,shutil,tempfile,unittest
from pathlib import Path
from pipeline.core import sha256
from pipeline.task_finish import register_intermediates,finish_reviewed_issue,retired_files
from pipeline.issue_archive import verify_issue

class TaskFinishTests(unittest.TestCase):
    def test_retired_root_and_outside_groups_are_rejected_before_enumeration(self):
        with tempfile.TemporaryDirectory() as temp:
            scope=Path(temp)/'issue';scope.mkdir();outside=Path(temp)/'outside';outside.mkdir()
            from unittest.mock import patch
            with patch('pipeline.task_finish.os.walk') as walk:
                files,kept=retired_files([scope,outside],scope=scope)
                self.assertEqual(files,[]);self.assertEqual(len(kept),2);walk.assert_not_called()
    def fixture(self,base,name='one'):
        run=base/'production/runs'/name;run.mkdir(parents=True)
        for filename,content in {'news.mp4':b'approved video','cue-000.mp4':b'rebuildable clip','news-no-bgm.mp4':b'remix input','original.wav':b'original recording','qa.png':b'unique proof'}.items():(run/filename).write_bytes(content)
        (run/'watch.html').write_text('<video src="news.mp4"></video>')
        (run/'daily.html').write_text('<a href="watch.html">play</a>')
        (run/'edition.json').write_text(json.dumps({'date':'2026-11-10','stories':[]}))
        register_intermediates(run,'2026-11-10',[run/'cue-000.mp4'])
        files={p.name:sha256(p) for p in run.iterdir() if p.is_file()}
        (run/'manifest.json').write_text(json.dumps(dict(status='rendered',date='2026-11-10',files=files,audio_inputs={})))
        return dict(date='2026-11-10',run_dir=str(run),video=str(run/'news.mp4'),player=str(run/'watch.html'),report=str(run/'daily.html'),edition=str(run/'edition.json'),manifest=str(run/'manifest.json'))

    def recycler(self,trash):
        def recycle(paths):
            result=[]
            for name in paths:
                p=Path(name);trash.mkdir(exist_ok=True);shutil.move(str(p),str(trash/(str(len(list(trash.iterdir())))+'-'+p.name)))
                result.append(dict(path=name,status='recycled'))
            return result
        return recycle

    def test_completion_recycles_registered_files_and_superseded_history_only(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'issue';root.mkdir();trash=Path(temp)/'bin'
            pointer=self.fixture(root);result=finish_reviewed_issue(pointer,root,recycler=self.recycler(trash))
            self.assertEqual(result['completion_status'],'complete')
            self.assertFalse((Path(pointer['run_dir'])/'cue-000.mp4').exists())
            for name in ['news-no-bgm.mp4','original.wav','qa.png']:self.assertTrue((Path(pointer['run_dir'])/name).exists())
            verify_issue(root,result['ledger'])
            two=self.fixture(root,'two');(Path(two['video'])).write_bytes(b'new approved version')
            # Refresh the producer manifest for the revised approved file.
            m=json.loads(Path(two['manifest']).read_text());m['files']['news.mp4']=sha256(two['video']);Path(two['manifest']).write_text(json.dumps(m))
            second=finish_reviewed_issue(two,root,recycler=self.recycler(trash))
            self.assertEqual(second['completion_status'],'complete')
            self.assertFalse((root/second['previous_current']/'news.mp4').exists())
            self.assertEqual((root/'deliverables/current/news.mp4').read_bytes(),b'new approved version')
            verify_issue(root,second['ledger'])
            self.assertEqual(json.loads((root/'latest.json').read_text())['video'],str(root/'deliverables/current/news.mp4'))

    def test_recycle_error_keeps_final_and_marks_cleanup_pending(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);pointer=self.fixture(root)
            result=finish_reviewed_issue(pointer,root,recycler=lambda paths:[dict(path=p,status='error',reason='bin unavailable') for p in paths])
            self.assertEqual(result['completion_status'],'pending_cleanup')
            self.assertTrue((Path(pointer['run_dir'])/'cue-000.mp4').exists())
            verify_issue(root,result['ledger'])

    def test_authoring_input_reference_is_kept_even_if_previously_registered(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);pointer=self.fixture(root);clip=Path(pointer['run_dir'])/'cue-000.mp4'
            (root/'editorial').mkdir();(root/'editorial/edition.json').write_text(json.dumps({'date':'2026-11-10','media':[{'path':str(clip)}]}))
            result=finish_reviewed_issue(pointer,root,recycler=self.recycler(root/'bin'))
            self.assertTrue(clip.exists());verify_issue(root,result['ledger'])

    def test_failed_finalization_never_calls_recycler(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);pointer=self.fixture(root)
            Path(pointer['report']).write_text('<img src="missing.jpg">')
            calls=[]
            with self.assertRaises(FileNotFoundError):finish_reviewed_issue(pointer,root,recycler=lambda paths:calls.append(paths))
            self.assertEqual(calls,[]);self.assertTrue((Path(pointer['run_dir'])/'cue-000.mp4').exists())

    def test_pointer_edition_inputs_are_protected_without_editorial_directory(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);one=self.fixture(root,'one');two=self.fixture(root,'two')
            original=Path(one['run_dir'])/'cue-000.mp4'
            Path(two['edition']).write_text(json.dumps({'date':'2026-11-10','stories':[{'media':[{'path':str(original)}]}]}))
            result=finish_reviewed_issue(two,root,recycler=self.recycler(root/'bin'))
            self.assertTrue(original.exists());self.assertEqual(result['completion_status'],'complete')
            verify_issue(root,result['ledger'])

    def test_changed_producer_artifact_is_retained_and_cleanup_stays_pending(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);pointer=self.fixture(root);clip=Path(pointer['run_dir'])/'cue-000.mp4';clip.write_bytes(b'edited after producer registration')
            result=finish_reviewed_issue(pointer,root,recycler=self.recycler(root/'bin'))
            self.assertTrue(clip.exists());self.assertEqual(result['completion_status'],'pending_cleanup')

    def test_nested_audio_manifest_uses_edition_base_for_active_wav(self):
        with tempfile.TemporaryDirectory() as temp:
            import wave
            root=Path(temp);old=self.fixture(root,'old');current=self.fixture(root,'new')
            run=Path(old['run_dir']);wav=run/'cue-000-padded.wav'
            with wave.open(str(wav),'wb') as audio:audio.setparams((1,2,24000,0,'NONE','not compressed'));audio.writeframes(b'\0'*480)
            register_intermediates(run,'2026-11-10',[wav]);manifest=json.loads(Path(old['manifest']).read_text());manifest['files'].update({'cleanup-candidates.json':sha256(run/'cleanup-candidates.json'),wav.name:sha256(wav)});Path(old['manifest']).write_text(json.dumps(manifest))
            editorial=root/'editorial';(editorial/'draft').mkdir(parents=True)
            (editorial/'edition.json').write_text(json.dumps({'date':'2026-11-10','stories':[],'audio_manifest':'draft/audio.json'}))
            (editorial/'draft/audio.json').write_text(json.dumps({'0':{'path':'../production/runs/old/cue-000-padded.wav'}}))
            result=finish_reviewed_issue(current,root,recycler=self.recycler(root/'bin'))
            self.assertTrue(wav.exists());self.assertEqual(result['completion_status'],'complete')
