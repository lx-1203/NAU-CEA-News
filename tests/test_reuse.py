import base64
import hashlib
import json
import runpy
import zipfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, Mock
from pipeline.github_archive import public_markdown, push_markdown, archive_edition
from pipeline.portable import portable_config, new_edition


class ReuseTests(unittest.TestCase):
    def edition(self):
        return dict(date='2026-11-09',title='校园科技新闻',stories=[dict(id='one',title='新工具公开',
            section='github',event_id='one-event',source_name='官方',source_url='https://example.com/news',
            published_at='2026-11-08T12:00:00+08:00',original_publication_date='2026-11-08',
            verified=True,verification_note='PRIVATE D:/internal/token',summary='提供文件整理功能。',
            why_it_matters='适合整理课程资料。',narration=['这是一款文件整理工具。'],visual_labels=['文件整理'],
            media=[dict(path='D:/private.wav',source_url='https://example.com/photo')])])

    def test_public_draft_has_sources_and_speech_but_no_internal_paths(self):
        text=public_markdown(self.edition())
        self.assertIn('2026-11-08',text);self.assertIn('https://example.com/news',text)
        self.assertIn('这是一款文件整理工具。',text)
        self.assertNotIn('PRIVATE',text);self.assertNotIn('D:/',text);self.assertNotIn('private.wav',text)

    def test_new_episode_has_eighteen_empty_unverified_slots(self):
        e=new_edition('2026-11-10')
        self.assertEqual(len(e['stories']),18)
        self.assertTrue(all(s['verified'] is False and s['narration']==[] for s in e['stories']))
        self.assertEqual(e['stories'][0]['original_publication_date'],'2026-11-09')

    def test_portable_profile_relocates_voices_and_runtime(self):
        source=json.loads((Path(__file__).resolve().parents[1]/'config/pipeline.json').read_text('utf8'))
        with tempfile.TemporaryDirectory() as temp:
            result=portable_config(source,Path(temp))
            self.assertNotIn('F:',json.dumps(result))
            self.assertTrue(Path(result['speech']['workbench']['project_dir']).is_relative_to(Path(temp)))
            self.assertEqual(result['speech']['workbench']['voices']['xiaoXu']['sha256'],source['speech']['workbench']['voices']['xiaoXu']['sha256'])

    def response(self,status,body):
        r=Mock();r.status_code=status;r.json.return_value=body;return r

    def test_github_idempotence_and_write_are_limited_to_daily_markdown(self):
        session=Mock()
        session.get.side_effect=[self.response(200,{'private':False,'default_branch':'main'}),self.response(404,{})]
        session.put.return_value=self.response(201,{'content':{'html_url':'https://github.com/o/r/blob/main/news/2026/11/2026-11-09.md'},'commit':{'sha':'abc'}})
        result=push_markdown('o/r','2026-11-09','稿件','test-token',session=session)
        self.assertEqual(result['status'],'uploaded')
        call=session.put.call_args
        self.assertTrue(call.args[0].endswith('/contents/news/2026/11/2026-11-09.md'))
        self.assertEqual(base64.b64decode(call.kwargs['json']['content']).decode(),'稿件')
        blob='稿件'.encode();git_sha=hashlib.sha1(b'blob '+str(len(blob)).encode()+b'\0'+blob).hexdigest()
        session=Mock();session.get.side_effect=[self.response(200,{'private':False,'default_branch':'main'}),self.response(200,{'sha':git_sha})]
        self.assertEqual(push_markdown('o/r','2026-11-09','稿件','test-token',session=session)['status'],'unchanged')
        session.put.assert_not_called()

    def test_private_repo_and_conflict_are_not_reported_as_uploaded(self):
        session=Mock();session.get.return_value=self.response(200,{'private':True})
        with self.assertRaises(ValueError):push_markdown('o/r','2026-11-09','稿件','test-token',session=session)
        session.put.assert_not_called()
        session=Mock();session.get.side_effect=[self.response(200,{'private':False,'default_branch':'main'}),self.response(200,{'sha':'old'})]
        session.put.return_value=self.response(409,{})
        with self.assertRaises(RuntimeError):push_markdown('o/r','2026-11-09','稿件','test-token',session=session)

    def test_unreviewed_or_changed_draft_cannot_publish(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);edition=root/'edition.json';edition.write_text(json.dumps(self.edition()),encoding='utf8')
            review=root/'review.json';review.write_text(json.dumps({'status':'passed','edition_sha256':'wrong'}),encoding='utf8')
            with self.assertRaises(ValueError):archive_edition(edition,review,root/'queue',{})

    def test_missing_repository_or_credentials_keeps_a_pending_copy(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);e=root/'edition.json';e.write_text(json.dumps(self.edition()),encoding='utf8')
            review=root/'review.json';review.write_text(json.dumps({'status':'passed','edition_sha256':hashlib.sha256(e.read_bytes()).hexdigest(),**{k:True for k in ['facts_checked','date_checked','dedup_checked','narration_checked']}}),encoding='utf8')
            with patch('pipeline.github_archive.validate_date_proof'):
                data=json.loads(e.read_text('utf8'));data['stories'][0].pop('section');e.write_text(json.dumps(data),encoding='utf8')
                checked=json.loads(review.read_text('utf8'));checked['edition_sha256']=hashlib.sha256(e.read_bytes()).hexdigest();review.write_text(json.dumps(checked),encoding='utf8')
                result=archive_edition(e,review,root/'queue',{},token='')
            self.assertEqual(result['status'],'pending_configuration')
            self.assertTrue((root/'queue/2026-11-09.md').is_file())

    def test_installer_rejects_zip_traversal_and_preserves_bad_existing_files(self):
        script=runpy.run_path(str(Path(__file__).resolve().parents[1]/'scripts/install_workbench.py'))
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);archive=root/'bad.zip'
            with zipfile.ZipFile(archive,'w') as z:z.writestr('../outside.txt','bad')
            with self.assertRaises(ValueError):script['extract_safe'](archive,root/'target')
            self.assertFalse((root/'outside.txt').exists())
            existing=root/'cached';existing.write_bytes(b'keep')
            with self.assertRaises(ValueError):script['download']('https://example.com/not-called',existing,'0'*64)
            self.assertEqual(existing.read_bytes(),b'keep')
