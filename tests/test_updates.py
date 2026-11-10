import hashlib
import io
import json
import os
import stat
import tempfile
import unittest
import warnings
import zipfile
from pathlib import Path
from unittest.mock import patch

from pipeline import updates


def digest(content):
    return hashlib.sha256(content).hexdigest()


class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='news 更新 ')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'project'
        self.source = Path(self.temp.name) / 'release'
        for directory in [self.root, self.source]:
            (directory / 'architecture').mkdir(parents=True)
            (directory / 'pipeline').mkdir()
        (self.root / 'config').mkdir()
        self.content = b'old code\n'
        (self.root / 'pipeline/demo.py').write_bytes(self.content)
        self.local = self.manifest('1.0.0', '1.0.0', {'pipeline/demo.py': self.content})
        self.write_manifest(self.root, self.local)
        self.publish('1.1.0', '1.0.1', {'pipeline/demo.py': b'new code\n'})
        self.configure(self.source.joinpath('release.json').as_uri())
        self.env = patch.dict(os.environ, {'NJAU_CEA_DATA_ROOT': ''})
        self.env.start()
        self.addCleanup(self.env.stop)

    def manifest(self, architecture, skill, files):
        return {'architecture_version': architecture, 'skill_version': skill,
                'files': {name: digest(value) for name, value in files.items()}}

    def write_manifest(self, root, manifest):
        target = root / ('release.json' if root == self.source else 'architecture/release.json')
        target.write_text(json.dumps(manifest), encoding='utf-8')

    def publish(self, architecture, skill, files):
        for name, value in files.items():
            target = self.source / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(value)
        self.remote = self.manifest(architecture, skill, files)
        self.write_manifest(self.source, self.remote)

    def configure(self, source):
        (self.root / 'config/updates.json').write_text(json.dumps({'source': source}))

    def archive(self, entries, **metadata):
        buffer = io.BytesIO()
        with warnings.catch_warnings(), zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as bundle:
            warnings.simplefilter('ignore', UserWarning)
            for name, content in entries:
                bundle.writestr(name, content)
        content = buffer.getvalue()
        (self.source / 'update.zip').write_bytes(content)
        self.remote['archive'] = dict(url='update.zip', sha256=digest(content), bytes=len(content), **metadata)
        self.write_manifest(self.source, self.remote)
        return content

    def assert_archive_rejected(self):
        with self.assertRaises(updates.UpdateError):
            updates.ensure_current(self.root)
        self.assertEqual((self.root / 'pipeline/demo.py').read_bytes(), self.content)
        self.assertEqual(json.loads((self.root / 'architecture/release.json').read_text()), self.local)
        self.assertFalse((self.root / 'pipeline/new.py').exists())
        self.assertFalse((self.root / 'runtime/update-backups').exists())

    def test_archive_upgrade_uses_only_manifest_and_verified_zip(self):
        files = {'pipeline/demo.py': b'new code\n', 'pipeline/new.py': b'new module\n'}
        self.publish('1.1.0', '1.1.0', files)
        self.archive([('pipeline/', b''), *files.items()])
        self.configure('https://example.test/main/release.json')
        self.remote['archive']['url'] = 'https://example.test/v1.1.0/updates/update.zip'
        responses = {self.remote['archive']['url']: (self.source / 'update.zip').read_bytes(),
                     'https://example.test/main/release.json': json.dumps(self.remote).encode()}
        with patch.object(updates, '_read_source', side_effect=lambda url, **kwargs: responses[url]) as reader:
            result = updates.ensure_current(self.root)
        self.assertEqual(reader.call_count, 2)
        self.assertEqual(result['status'], 'updated')
        for name, content in files.items():
            self.assertEqual((self.root / name).read_bytes(), content)
        self.assertEqual(json.loads((self.root / 'architecture/release.json').read_text()), self.remote)
        self.assertEqual((Path(result['backup']) / 'pipeline/demo.py').read_bytes(), self.content)

    def test_archive_hash_and_size_mismatch_never_install_or_fallback(self):
        for field, value in [('sha256', '0' * 64), ('bytes', 1)]:
            with self.subTest(field=field):
                self.archive([('pipeline/demo.py', b'new code\n')])
                self.remote['archive'][field] = value
                self.write_manifest(self.source, self.remote)
                self.assert_archive_rejected()

    def test_archive_hash_is_checked_before_zip_parsing(self):
        self.archive([('pipeline/demo.py', b'new code\n')])
        self.remote['archive']['sha256'] = '0' * 64
        self.write_manifest(self.source, self.remote)
        with patch.object(updates.zipfile, 'ZipFile') as parser:
            self.assert_archive_rejected()
        parser.assert_not_called()

    def test_archive_read_failure_preserves_installation(self):
        self.archive([('pipeline/demo.py', b'new code\n')])
        with patch.object(updates, '_read_source', side_effect=[json.dumps(self.remote).encode(),
                                                              OSError('archive read denied')]):
            self.assert_archive_rejected()

    def test_archive_corrupt_compressed_data_is_an_update_error(self):
        content = bytearray(self.archive([('pipeline/demo.py', b'new code\n')]))
        with zipfile.ZipFile(io.BytesIO(content)) as bundle:
            entry = bundle.infolist()[0]
            offset = entry.header_offset + 30 + len(entry.filename.encode()) + len(entry.extra)
        content[offset] = 0xff
        (self.source / 'update.zip').write_bytes(content)
        self.remote['archive']['sha256'] = digest(content)
        self.write_manifest(self.source, self.remote)
        self.assert_archive_rejected()

    def test_archive_rejects_unsafe_duplicate_unlisted_missing_and_bad_hash_members(self):
        cases = [
            [('pipeline/demo.py', b'new code\n'), ('../escape.py', b'bad')],
            [('pipeline/demo.py', b'new code\n'), ('pipeline/../escape.py', b'bad')],
            [('pipeline/demo.py', b'new code\n'), ('pipeline\\escape.py', b'bad')],
            [('pipeline/demo.py', b'new code\n'), ('/pipeline/escape.py', b'bad')],
            [('pipeline/demo.py', b'new code\n'), ('pipeline/demo.py', b'new code\n')],
            [('pipeline/demo.py', b'new code\n'), ('pipeline/DEMO.py', b'new code\n')],
            [('pipeline/demo.py', b'new code\n'), ('pipeline/unlisted.py', b'bad')],
            [('pipeline/demo.py', b'new code\n'), ('pipeline/extra/', b'')],
            [('pipeline/demo.py', b'new code\n'), ('pipeline/../', b'')],
            [('pipeline/', b'')],
            [('pipeline/demo.py', b'wrong content')],
        ]
        for entries in cases:
            with self.subTest(names=[name for name, _ in entries]):
                self.archive(entries)
                self.assert_archive_rejected()
        self.assertFalse((self.root.parent / 'escape.py').exists())

    def test_archive_rejects_symlink_reparse_and_nonregular_members(self):
        for mode, attributes in [(stat.S_IFLNK | 0o777, 0), (stat.S_IFIFO | 0o600, 0),
                                 (stat.S_IFREG | 0o644, 0x400)]:
            with self.subTest(mode=mode, attributes=attributes):
                entry = zipfile.ZipInfo('pipeline/demo.py')
                entry.create_system = 3
                entry.external_attr = mode << 16 | attributes
                self.archive([(entry, b'new code\n')])
                self.assert_archive_rejected()

    def test_archive_rejects_wrong_format_and_bounded_expansion(self):
        (self.source / 'update.zip').write_bytes(b'not a zip archive')
        self.remote['archive'] = {'url': 'update.zip', 'sha256': digest(b'not a zip archive')}
        self.write_manifest(self.source, self.remote)
        self.assert_archive_rejected()
        self.archive([('pipeline/demo.py', b'x' * 100)])
        with patch.object(updates, 'MAX_ARCHIVE_UNCOMPRESSED', 99, create=True):
            self.assert_archive_rejected()
        self.remote['archive'].pop('bytes')
        self.write_manifest(self.source, self.remote)
        with patch.object(updates, 'MAX_ARCHIVE_BYTES', 10, create=True):
            self.assert_archive_rejected()

    def test_current_manifest_validates_archive_metadata_without_reading_archive(self):
        for archive in [None, {}, {'url': 'http://example.test/update.zip', 'sha256': '0' * 64},
                        {'url': '../update.zip', 'sha256': '0' * 64},
                        {'url': '//example.test/update.zip', 'sha256': '0' * 64},
                        {'url': 'https://user:secret@example.test/update.zip', 'sha256': '0' * 64},
                        {'url': 'https://example.test/update.zip?q=1', 'sha256': '0' * 64},
                        {'url': 'file:relative.zip', 'sha256': '0' * 64},
                        {'url': 'update.zip', 'sha256': 1},
                        {'url': 'update.zip', 'sha256': '0' * 64, 'bytes': True},
                        {'url': 'update.zip', 'sha256': '0' * 64, 'bytes': -1}]:
            with self.subTest(archive=archive):
                self.write_manifest(self.source, dict(self.local, archive=archive))
                self.assert_archive_rejected()

    def test_relative_and_file_archive_urls_and_optional_size(self):
        self.archive([('pipeline/demo.py', b'new code\n')])
        self.remote['archive'].pop('bytes')
        for url in ['update.zip', (self.source / 'update.zip').as_uri()]:
            with self.subTest(url=url):
                self.write_manifest(self.root, self.local)
                (self.root / 'pipeline/demo.py').write_bytes(self.content)
                self.remote['archive']['url'] = url
                self.write_manifest(self.source, self.remote)
                self.assertEqual(updates.ensure_current(self.root)['status'], 'updated')
        with patch.object(updates, '_read_source', wraps=updates._read_source) as reader:
            self.assertEqual(updates.ensure_current(self.root)['status'], 'current')
        self.assertEqual(reader.call_count, 1)

    def test_local_upgrade_records_manifest_and_backup(self):
        result = updates.ensure_current(self.root)
        self.assertEqual(result['status'], 'updated')
        self.assertEqual(result['architecture_version'], '1.1.0')
        self.assertEqual(result['skill_version'], '1.0.1')
        self.assertEqual((self.root / 'pipeline/demo.py').read_bytes(), b'new code\n')
        self.assertEqual(json.loads((self.root / 'architecture/release.json').read_text()), self.remote)
        self.assertEqual((Path(result['backup']) / 'pipeline/demo.py').read_bytes(), self.content)
        self.assertFalse((self.root / 'runtime/update.lock').exists())

    def test_reads_source_again_instead_of_cached_current(self):
        updates.ensure_current(self.root)
        (self.source / 'release.json').unlink()
        with self.assertRaisesRegex(updates.UpdateError, 'source|read'):
            updates.ensure_current(self.root)

    def test_bad_hash_does_not_write_any_managed_file(self):
        self.publish('1.1.0', '1.0.1', {'pipeline/demo.py': b'valid first download', 'pipeline/new.py': b'expected second'})
        (self.source / 'pipeline/new.py').write_bytes(b'broken transfer')
        with self.assertRaisesRegex(updates.UpdateError, 'hash'):
            updates.ensure_current(self.root)
        self.assertEqual((self.root / 'pipeline/demo.py').read_bytes(), self.content)
        self.assertFalse((self.root / 'pipeline/new.py').exists())
        self.assertEqual(json.loads((self.root / 'architecture/release.json').read_text()), self.local)

    def test_local_modification_refuses_update(self):
        (self.root / 'pipeline/demo.py').write_bytes(b'user edits')
        with self.assertRaisesRegex(updates.UpdateError, 'local|modified|conflict'):
            updates.ensure_current(self.root)
        self.assertEqual((self.root / 'pipeline/demo.py').read_bytes(), b'user edits')

    def test_existing_unmanaged_file_refuses_overwrite(self):
        (self.root / 'pipeline/extra.py').write_bytes(b'user file')
        self.publish('1.1.0', '1.0.1', {'pipeline/demo.py': b'new', 'pipeline/extra.py': b'upstream'})
        with self.assertRaisesRegex(updates.UpdateError, 'local|unmanaged|conflict'):
            updates.ensure_current(self.root)

    def test_missing_configuration_and_bad_scheme_are_errors(self):
        (self.root / 'config/updates.json').unlink()
        with self.assertRaisesRegex(updates.UpdateError, 'configured'):
            updates.ensure_current(self.root)
        self.configure('http://example.test/release.json')
        with self.assertRaisesRegex(updates.UpdateError, 'HTTPS|scheme'):
            updates.ensure_current(self.root)

    def test_local_source_overrides_shared_source(self):
        self.configure('https://invalid.example/release.json')
        (self.root / 'config/updates.local.json').write_text(json.dumps({'source': (self.source / 'release.json').as_uri()}))
        self.assertEqual(updates.ensure_current(self.root)['status'], 'updated')

    def test_downgrade_and_unversioned_content_change_rejected(self):
        for arch, skill in [('0.9.0', '1.0.1'), ('1.1.0', '0.9.0'), ('1.0.0', '1.0.0')]:
            self.publish(arch, skill, {'pipeline/demo.py': b'different'})
            with self.assertRaisesRegex(updates.UpdateError, 'rollback|version'):
                updates.ensure_current(self.root)

    def test_lock_is_never_removed_when_owned_by_another_process(self):
        (self.root / 'runtime').mkdir()
        lock = self.root / 'runtime/update.lock'
        lock.write_text('other process')
        with self.assertRaisesRegex(updates.UpdateError, 'lock'):
            updates.ensure_current(self.root)
        self.assertEqual(lock.read_text(), 'other process')

    def test_render_lock_blocks_update(self):
        for relative in ['outputs/daily/.render.lock', 'data/.render.lock']:
            lock = self.root / relative
            lock.parent.mkdir(parents=True, exist_ok=True)
            lock.touch()
            with self.assertRaisesRegex(updates.UpdateError, 'render'):
                updates.ensure_current(self.root)
            lock.unlink()

    def test_external_data_root_render_lock_blocks_update(self):
        data = Path(self.temp.name) / 'external data'
        data.mkdir()
        (data / '.render.lock').touch()
        with patch.dict(os.environ, {'NJAU_CEA_DATA_ROOT': str(data)}):
            with self.assertRaisesRegex(updates.UpdateError, 'render'):
                updates.ensure_current(self.root)

    def test_rejects_unsafe_and_user_data_paths(self):
        for name in ['../escape', 'data/x', 'outputs/x', 'runtime/x', '.venv/x', '.tools/x',
                     'config/storage.local.json', 'config/updates.local.json',
                     'docs/2026-11-10-report.md', 'pipeline/../data/x', 'C:/bad',
                     'pipeline\\bad.py', 'pipeline/CON', 'pipeline/file.py:stream']:
            remote = self.manifest('1.1.0', '1.0.1', {name: b'x'})
            self.write_manifest(self.source, remote)
            with self.subTest(name=name), self.assertRaises(updates.UpdateError):
                updates.ensure_current(self.root)
        self.assertEqual((self.root / 'pipeline/demo.py').read_bytes(), self.content)

    def test_symlink_ancestor_rejected(self):
        link = self.root / 'scripts'
        outside = Path(self.temp.name) / 'outside'
        outside.mkdir()
        try:
            link.symlink_to(outside, target_is_directory=True)
        except OSError:
            self.skipTest('symlink creation not permitted on this host')
        self.publish('1.1.0', '1.0.1', {'pipeline/demo.py': b'new', 'scripts/new.py': b'bad'})
        with self.assertRaisesRegex(updates.UpdateError, 'link|junction'):
            updates.ensure_current(self.root)
        self.assertFalse((outside / 'new.py').exists())

    def test_apply_failure_rolls_back_files_and_manifest(self):
        self.publish('1.1.0', '1.0.1', {'pipeline/new.py': b'newly created'})
        original = updates.os.replace
        def fail_install(source, destination):
            if Path(destination) == self.root / 'architecture/release.json':
                raise OSError('simulated manifest write failure')
            return original(source, destination)
        with patch.object(updates.os, 'replace', side_effect=fail_install):
            with self.assertRaisesRegex(updates.UpdateError, 'rolled back'):
                updates.ensure_current(self.root)
        self.assertEqual((self.root / 'pipeline/demo.py').read_bytes(), self.content)
        self.assertFalse((self.root / 'pipeline/new.py').exists())
        self.assertEqual(json.loads((self.root / 'architecture/release.json').read_text()), self.local)

    def test_explicit_offline_is_reported_as_offline(self):
        result = updates.ensure_current(self.root, offline=True)
        self.assertEqual(result['status'], 'offline')

    def test_same_version_still_rejects_local_modification(self):
        self.write_manifest(self.source, self.local)
        (self.root / 'pipeline/demo.py').write_bytes(b'edited same version')
        with self.assertRaisesRegex(updates.UpdateError, 'Local modified'):
            updates.ensure_current(self.root)

    def test_current_and_check_only_never_write_managed_files(self):
        result = updates.ensure_current(self.root, apply=False)
        self.assertEqual(result['status'], 'available')
        self.assertEqual((self.root / 'pipeline/demo.py').read_bytes(), self.content)
        self.write_manifest(self.source, self.local)
        self.assertEqual(updates.ensure_current(self.root)['status'], 'current')

    def test_https_unreachable_is_an_error_and_preserves_installation(self):
        self.configure('https://updates.example.invalid/release.json')
        with patch.object(updates.urllib.request, 'urlopen', side_effect=OSError('unreachable')):
            with self.assertRaisesRegex(updates.UpdateError, 'source.*unreachable'):
                updates.ensure_current(self.root)
        self.assertEqual((self.root / 'pipeline/demo.py').read_bytes(), self.content)

    def test_publisher_copies_only_hashed_manifest_allowlist(self):
        (self.root / 'config/storage.local.json').write_text('{"data_root":"secret"}')
        output = Path(self.temp.name) / 'published'
        result = updates.publish_local_release(self.root, output)
        self.assertEqual(result['files'], 1)
        self.assertEqual((output / 'pipeline/demo.py').read_bytes(), self.content)
        self.assertEqual(json.loads((output / 'release.json').read_text()), self.local)
        self.assertFalse((output / 'config').exists())
        with self.assertRaisesRegex(updates.UpdateError, 'empty'):
            updates.publish_local_release(self.root, output)

    def test_publisher_hash_failure_leaves_output_absent(self):
        (self.root / 'pipeline/demo.py').write_bytes(b'changed')
        output = Path(self.temp.name) / 'not published'
        with self.assertRaisesRegex(updates.UpdateError, 'hash'):
            updates.publish_local_release(self.root, output)
        self.assertFalse(output.exists())

    def test_publisher_with_archive_creates_self_contained_loose_file_channel(self):
        self.archive([('pipeline/demo.py', b'new code\n')])
        updates.ensure_current(self.root)
        original = (self.root / 'architecture/release.json').read_bytes()
        output = Path(self.temp.name) / 'published archive release'
        updates.publish_local_release(self.root, output)
        published = json.loads((output / 'release.json').read_text())
        self.assertNotIn('archive', published)
        self.assertEqual((self.root / 'architecture/release.json').read_bytes(), original)
        self.write_manifest(self.root, self.local)
        (self.root / 'pipeline/demo.py').write_bytes(self.content)
        self.configure((output / 'release.json').as_uri())
        with patch.object(updates.urllib.request, 'urlopen', side_effect=AssertionError('Network used')):
            self.assertEqual(updates.ensure_current(self.root)['status'], 'updated')
        self.assertEqual((self.root / 'pipeline/demo.py').read_bytes(), b'new code\n')
        self.assertEqual(json.loads((self.root / 'architecture/release.json').read_text()), published)

    def test_windows_junction_ancestor_rejected(self):
        if os.name != 'nt':
            self.skipTest('Windows junction check')
        import subprocess
        outside = Path(self.temp.name) / 'junction outside'
        outside.mkdir()
        junction = self.root / 'scripts'
        process = subprocess.run(['cmd', '/c', 'mklink', '/J', str(junction), str(outside)], capture_output=True)
        if process.returncode:
            self.skipTest('junction creation not permitted on this host')
        try:
            self.publish('1.1.0', '1.0.1', {'scripts/new.py': b'bad'})
            with self.assertRaisesRegex(updates.UpdateError, 'junction'):
                updates.ensure_current(self.root)
            self.assertFalse((outside / 'new.py').exists())
        finally:
            junction.rmdir()

    def test_unknown_file_types_and_malformed_paths_are_rejected(self):
        for name in ['pipeline/star*.py', 'pipeline/question?.py', 'pipeline/bad\x00.py',
                     'pipeline/quote".py', 'pipeline/<file>.py', 'pipeline/name|.py']:
            self.write_manifest(self.source, self.manifest('1.1.0', '1.0.1', {name: b'x'}))
            with self.subTest(name=name), self.assertRaises(updates.UpdateError):
                updates.ensure_current(self.root)

    def test_project_relative_source_and_tests_are_supported(self):
        import shutil
        channel = self.root / 'architecture/channel'
        shutil.copytree(self.source, channel)
        self.configure('architecture/channel/release.json')
        self.assertEqual(updates.ensure_current(self.root)['status'], 'updated')
        self.assertEqual(updates._safe_name('tests/test_example.py'), 'tests/test_example.py')

    def test_relative_source_cannot_escape_project(self):
        for source in ['../release.json', '/absolute/release.json', 'file:relative.json',
                       'architecture/../release.json', 'architecture\\release.json']:
            self.configure(source)
            with self.subTest(source=source), self.assertRaises(updates.UpdateError):
                updates.ensure_current(self.root)

    def test_manifest_file_directory_collision_is_rejected(self):
        self.write_manifest(self.source, self.manifest('1.1.0', '1.0.1', {
            'pipeline/a': b'a', 'pipeline/a-other': b'b', 'pipeline/a/child.py': b'c'}))
        with self.assertRaisesRegex(updates.UpdateError, 'collision'):
            updates.ensure_current(self.root)

    def current_receipt(self):
        self.write_manifest(self.source, self.local)
        return updates.ensure_current(self.root)

    def test_production_guard_excludes_updater_and_releases_after_exception(self):
        receipt = self.current_receipt()
        with self.assertRaisesRegex(RuntimeError, 'render failed'):
            with updates.production_guard(self.root, receipt):
                with self.assertRaisesRegex(updates.UpdateError, 'lock'):
                    updates.ensure_current(self.root)
                raise RuntimeError('render failed')
        self.assertFalse((self.root / 'runtime/update.lock').exists())
        self.assertEqual(updates.ensure_current(self.root)['status'], 'current')

    def test_running_update_excludes_production_guard(self):
        receipt = self.current_receipt()
        read_source = updates._read_source
        attempts = []
        def read_during_update(url):
            with self.assertRaisesRegex(updates.UpdateError, 'lock'):
                with updates.production_guard(self.root, receipt):
                    self.fail('Production entered while an update owns the shared lock')
            attempts.append(url)
            return read_source(url)
        with patch.object(updates, '_read_source', side_effect=read_during_update):
            updates.ensure_current(self.root)
        self.assertTrue(attempts)

    def test_guard_rejects_release_changed_since_check(self):
        receipt = self.current_receipt()
        newer = dict(self.local, architecture_version='1.1.0')
        self.write_manifest(self.root, newer)
        with self.assertRaisesRegex(updates.UpdateError, 'stale|restart'):
            with updates.production_guard(self.root, receipt):
                self.fail('Stale production receipt was accepted')
        self.assertFalse((self.root / 'runtime/update.lock').exists())

    def test_guard_rechecks_local_integrity_and_legacy_render_lock(self):
        receipt = self.current_receipt()
        (self.root / 'pipeline/demo.py').write_bytes(b'changed after freshness check')
        with self.assertRaisesRegex(updates.UpdateError, 'modified'):
            with updates.production_guard(self.root, receipt):
                self.fail('Changed local content was accepted')
        (self.root / 'pipeline/demo.py').write_bytes(self.content)
        lock = self.root / 'outputs/daily/.render.lock'
        lock.parent.mkdir(parents=True)
        lock.touch()
        with self.assertRaisesRegex(updates.UpdateError, 'render'):
            with updates.production_guard(self.root, receipt):
                self.fail('Legacy render lock was ignored')

    def test_guard_rejects_offline_and_restart_pending_receipts(self):
        receipt = self.current_receipt()
        for changed in [dict(receipt, status='offline'), dict(receipt, rerun_required=True)]:
            with self.subTest(receipt=changed), self.assertRaisesRegex(updates.UpdateError, 'receipt|restart'):
                with updates.production_guard(self.root, changed):
                    self.fail('Unverified or restart-pending receipt was accepted')


if __name__ == '__main__':
    unittest.main()
