import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

from pipeline.core import ROOT
from pipeline.updates import UpdateError

spec = importlib.util.spec_from_file_location('freeze_release', ROOT / 'scripts/freeze_release.py')
freeze_release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(freeze_release)


class ReleaseVersionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.names = ['pipeline/demo.py', 'skills/nau-cea-daily-video/SKILL.md']
        for name in self.names:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('original', encoding='utf8')
        (self.root / 'architecture').mkdir()
        (self.root / 'architecture/managed-files.json').write_text(
            json.dumps({'files': self.names}), encoding='utf8')
        freeze_release.freeze(self.root, '1.2.0', '1.2.0')
        self.before = (self.root / 'architecture/release.json').read_bytes()

    def test_skill_change_requires_skill_increment_even_with_architecture_increment(self):
        (self.root / self.names[1]).write_text('new rule', encoding='utf8')
        with self.assertRaisesRegex(UpdateError, 'skill version'):
            freeze_release.freeze(self.root, '1.2.1', '1.2.0')
        self.assertEqual((self.root / 'architecture/release.json').read_bytes(), self.before)

    def test_managed_change_requires_architecture_increment_even_with_skill_increment(self):
        (self.root / self.names[0]).write_text('new code', encoding='utf8')
        with self.assertRaisesRegex(UpdateError, 'architecture version'):
            freeze_release.freeze(self.root, '1.2.0', '1.2.1')
        self.assertEqual((self.root / 'architecture/release.json').read_bytes(), self.before)

    def test_removing_skill_resource_requires_skill_increment(self):
        (self.root / 'architecture/managed-files.json').write_text(
            json.dumps({'files': [self.names[0]]}), encoding='utf8')
        with self.assertRaisesRegex(UpdateError, 'skill version'):
            freeze_release.freeze(self.root, '1.2.1', '1.2.0')

    def test_both_incremented_accepts_skill_change(self):
        (self.root / self.names[1]).write_text('new rule', encoding='utf8')
        result = freeze_release.freeze(self.root, '1.2.1', '1.2.1')
        self.assertEqual(result['architecture_version'], '1.2.1')
        self.assertEqual(result['skill_version'], '1.2.1')

    def test_code_only_patch_preserves_unchanged_skill_version(self):
        (self.root / self.names[0]).write_text('new code', encoding='utf8')
        result = freeze_release.freeze(self.root, '1.2.1', '1.2.0')
        self.assertEqual(result['skill_version'], '1.2.0')

    def test_unchanged_freeze_is_idempotent(self):
        freeze_release.freeze(self.root, '1.2.0', '1.2.0')
        self.assertEqual((self.root / 'architecture/release.json').read_bytes(), self.before)


if __name__ == '__main__':
    unittest.main()
