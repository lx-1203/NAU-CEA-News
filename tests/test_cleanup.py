import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from pipeline.cleanup import prepare_cleanup, execute_cleanup
import pipeline.cleanup as cleanup


class CleanupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'issue'
        self.root.mkdir()
        self.final = self.root / 'final.mp4'
        self.final.write_bytes(b'verified final')
        self.old = self.root / 'retired.mp4'
        self.old.write_bytes(b'explicitly retired')
        self.manifest = self.root / 'manifest.json'
        self.manifest.write_text(json.dumps({'files': {'final.mp4': {
            'sha256': hashlib.sha256(self.final.read_bytes()).hexdigest(),
            'bytes': self.final.stat().st_size}}}), encoding='utf8')
        self.bin = Path(self.temp.name) / 'fake-bin'
        self.bin.mkdir()

    def prepare(self, paths=None, **kw):
        return prepare_cleanup(self.root, self.root, self.manifest,
                               [self.old] if paths is None else paths, **kw)

    def recycle(self, paths):
        receipts = []
        for path in paths:
            shutil.move(path, self.bin / Path(path).name)
            receipts.append({'path': path, 'status': 'recycled'})
        return receipts

    def test_planning_skips_do_not_report_fully_completed(self):
        outside=self.root.parent/'outside-discard.txt';outside.write_text('keep',encoding='utf8')
        state=self.prepare([outside])
        result=execute_cleanup(state['state_path'],self.recycle)
        self.assertFalse(result['completed']);self.assertTrue(outside.exists())

    def test_metadata_cannot_overwrite_final_or_protected_directory(self):
        before=self.final.read_bytes()
        for state in [self.final,self.manifest]:
            with self.assertRaises(ValueError):self.prepare(state_path=state)
        protected=self.root/'proof';protected.mkdir()
        with self.assertRaises(ValueError):self.prepare(protected_paths=[protected],state_path=protected/'new/state.json')
        self.assertEqual(self.final.read_bytes(),before)

    def test_tampered_log_path_cannot_append_to_final(self):
        state=self.prepare();before=self.final.read_bytes()
        state['log_path']=str(self.final);Path(state['state_path']).write_text(json.dumps(state),encoding='utf8')
        with self.assertRaises(ValueError):execute_cleanup(state['state_path'],self.recycle)
        self.assertEqual(self.final.read_bytes(),before);self.assertTrue(self.old.exists())

    def test_success_and_idempotence(self):
        state = self.prepare()
        result = execute_cleanup(state['state_path'], self.recycle)
        self.assertEqual(result['count'], 1)
        self.assertTrue(result['completed'])
        self.assertEqual(result['moved_bytes'], len(b'explicitly retired'))
        self.assertFalse(self.old.exists())
        self.assertTrue(self.final.exists())
        self.assertEqual(execute_cleanup(state['state_path'], self.recycle)['count'], 0)
        self.assertEqual(self.prepare()['candidates'], [])

    def test_manifest_failure_blocks_plan(self):
        self.final.write_bytes(b'bad final')
        with self.assertRaises(ValueError):
            self.prepare()
        self.final.unlink()
        with self.assertRaises(ValueError):
            self.prepare()
        self.assertTrue(self.old.exists())

    def test_protection_and_candidate_registry(self):
        source = self.root / 'original.wav'
        source.write_bytes(b'keep')
        state = self.prepare([self.final, self.manifest, source], protected_paths=[source])
        self.assertEqual(state['candidates'], [])
        self.assertEqual(len(state['skipped']), 3)
        self.assertTrue(self.old.exists())

    def test_scope_and_manifest_escape(self):
        with self.assertRaises(ValueError):
            prepare_cleanup(Path('relative'), self.root, self.manifest, [self.old])
        state = self.prepare([self.root, self.root / '..' / 'outside.mp4'])
        self.assertEqual(state['candidates'], [])
        self.manifest.write_text(json.dumps({'files': {'../outside': 'a' * 64}}))
        with self.assertRaises(ValueError):
            self.prepare()

    def test_changed_candidate_is_skipped(self):
        state = self.prepare()
        self.old.write_bytes(b'new writer output')
        result = execute_cleanup(state['state_path'], self.recycle)
        self.assertEqual(result['count'], 0)
        self.assertFalse(result['completed'])
        self.assertTrue(self.old.exists())

    def test_changed_final_and_active_locks_block_execution(self):
        state = self.prepare()
        lock = self.root / '.render.lock'
        lock.write_text('running')
        self.assertEqual(execute_cleanup(state['state_path'], self.recycle, [lock])['status'], 'blocked')
        lock.unlink()
        self.final.write_bytes(b'changed')
        self.assertEqual(execute_cleanup(state['state_path'], self.recycle)['status'], 'blocked')
        self.assertTrue(self.old.exists())

    def test_recycler_error_has_no_delete_fallback(self):
        state = self.prepare()
        def fail(paths):
            raise OSError('Recycle Bin unavailable')
        result = execute_cleanup(state['state_path'], fail)
        self.assertEqual(result['count'], 0)
        self.assertTrue(self.old.exists())
        self.assertIn('Recycle Bin unavailable', (self.root / 'cleanup-log.jsonl').read_text())

    def test_missing_without_success_receipt_is_not_claimed(self):
        state = self.prepare()
        self.old.unlink()
        result = execute_cleanup(state['state_path'], self.recycle)
        self.assertEqual(result['count'], 0)
        self.assertIn('missing', str(result['skipped']).lower())

    def test_protected_blobs_hashed_only_before_and_after_execution(self):
        dependencies = self.root / 'dependencies'
        dependencies.mkdir()
        dependency = dependencies / 'image.png'
        dependency.write_bytes(b'protected dependency')
        others = [self.root / f'old-{i}.mp4' for i in range(4)]
        for path in others:
            path.write_bytes(b'old')
        state = self.prepare([self.old, *others], protected_paths=[dependencies])
        with patch.object(cleanup, '_snapshot', wraps=cleanup._snapshot) as snapshot:
            result = execute_cleanup(state['state_path'], self.recycle)
        self.assertTrue(result['completed'])
        for protected in [self.final, self.manifest, dependency]:
            self.assertEqual(sum(Path(call.args[0]) == protected for call in snapshot.call_args_list), 2)

    def test_custom_state_keeps_log_in_task_directory(self):
        state_path = self.root / 'tasks' / 'cleanup-state.json'
        state = self.prepare(state_path=state_path)
        self.assertEqual(Path(state['log_path']), state_path.with_name('cleanup-log.jsonl'))
        self.assertTrue(execute_cleanup(state_path, self.recycle)['completed'])
        self.assertFalse((self.root / 'cleanup-log.jsonl').exists())

    def test_protected_change_during_execution_blocks_next_candidate(self):
        other = self.root / 'other.mp4'
        other.write_bytes(b'old')
        state = self.prepare([self.old, other])
        def recycle_and_change(paths):
            receipts = self.recycle(paths)
            self.final.write_bytes(b'changed by writer')
            return receipts
        result = execute_cleanup(state['state_path'], recycle_and_change)
        self.assertEqual(result['count'], 1)
        self.assertFalse(result['completed'])
        self.assertEqual(result['status'], 'blocked')
        self.assertEqual(sum(p.exists() for p in [self.old, other]), 1)

    @unittest.skipUnless(os.name == 'nt', 'Windows native subprocess contract')
    def test_native_subprocess_uses_explicit_utf8_for_chinese_paths(self):
        old = self.old.with_name('旧 片段.mp4')
        self.old.rename(old)
        expected = [{'path': str(old), 'status': 'error', 'reason': '回收站不可用'}]
        def invoke(command, **kwargs):
            request = json.loads(Path(command[-1]).read_text(encoding='utf8'))
            self.assertEqual(request['paths'], [str(old)])
            self.assertEqual(kwargs['encoding'], 'utf8')
            return subprocess.CompletedProcess(command, 0, json.dumps(expected, ensure_ascii=False))
        with patch.object(cleanup.subprocess, 'run', side_effect=invoke):
            self.assertEqual(cleanup._native_recycle([str(old)], self.root), expected)

    def test_lock_created_during_recycling_defers_remaining_files(self):
        other = self.root / 'other-retired.mp4'
        other.write_bytes(b'old')
        state = self.prepare([self.old, other])
        lock = self.root / '.render.lock'
        def recycle_and_lock(paths):
            receipts = self.recycle(paths)
            lock.write_text('new render')
            return receipts
        result = execute_cleanup(state['state_path'], recycle_and_lock, [lock])
        self.assertEqual(result['count'], 1)
        self.assertEqual(result['status'], 'blocked')
        self.assertEqual(sum(p.exists() for p in [self.old, other]), 1)

    def test_missing_dependency_and_exclusive_cleanup_lock(self):
        dependency = self.root / 'texture.png'
        dependency.write_bytes(b'texture')
        state = self.prepare(protected_paths=[dependency])
        lock = Path(state['state_path'] + '.lock')
        lock.write_text('another cleanup')
        self.assertEqual(execute_cleanup(state['state_path'], self.recycle)['status'], 'blocked')
        self.assertTrue(lock.exists())
        lock.unlink()
        dependency.unlink()
        self.assertEqual(execute_cleanup(state['state_path'], self.recycle)['status'], 'blocked')
        self.assertTrue(self.old.exists())

    def test_symlink_candidate_and_ancestor_are_skipped(self):
        target = Path(self.temp.name) / 'outside'
        target.mkdir()
        (target / 'old').write_bytes(b'outside')
        link = self.root / 'linked'
        try:
            link.symlink_to(target, target_is_directory=True)
        except OSError:
            if os.name != 'nt':
                self.skipTest('symlink privilege unavailable')
            junction = subprocess.run(['cmd.exe', '/c', 'mklink', '/J', str(link), str(target)],
                                      capture_output=True, text=True)
            if junction.returncode:
                self.skipTest('symlink and junction creation unavailable')
        state = self.prepare([link / 'old'])
        self.assertEqual(state['candidates'], [])
        self.assertTrue((target / 'old').exists())


if __name__ == '__main__':
    unittest.main()
