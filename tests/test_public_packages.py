import importlib.util,json,tempfile,unittest,zipfile
from pathlib import Path
from pipeline.core import ROOT,sha256

def load(name):
    spec=importlib.util.spec_from_file_location(name,ROOT/'scripts'/f'{name}.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

class PublicPackageTests(unittest.TestCase):
    def test_public_export_only_copies_explicit_framework_and_templates(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'source';(root/'architecture').mkdir(parents=True);(root/'config').mkdir();(root/'pipeline').mkdir()
            (root/'pipeline/demo.py').write_text('pass\n');(root/'config/pipeline.example.json').write_text('{"portable_profile":true}')
            (root/'config/github.example.json').write_text('{"repository":null}')
            (root/'private-song.mp3').write_bytes(b'never publish');(root/'config/updates.local.json').write_text('{"secret":"private"}')
            names=['pipeline/demo.py','config/pipeline.example.json','config/github.example.json']
            release=dict(architecture_version='1.1.0',skill_version='1.1.0',files={n:sha256(root/n) for n in names})
            (root/'architecture/release.json').write_text(json.dumps(release))
            out=Path(temp)/'Framework-v1.1.0';result=load('build_framework_package').build(out,root)
            self.assertEqual(Path(result['zip']).name,'Framework-v1.1.0.zip')
            with zipfile.ZipFile(result['zip']) as archive:
                self.assertIsNone(archive.testzip());self.assertFalse(any('private-song' in n or '.local.json' in n for n in archive.namelist()))
            self.assertTrue((out/'docs/TODO.md').exists());self.assertTrue((out/'config/pipeline.json').exists())

    def test_online_archive_is_reproducible_and_exactly_matches_managed_files(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'architecture').mkdir();(root/'pipeline').mkdir();(root/'pipeline/demo.py').write_bytes(b'code')
            release=dict(architecture_version='1.1.0',skill_version='1.1.0',files={'pipeline/demo.py':sha256(root/'pipeline/demo.py')})
            (root/'architecture/release.json').write_text(json.dumps(release))
            module=load('build_online_release');first=module.build(root);second=module.build(root)
            self.assertEqual(first['archive_sha256'],second['archive_sha256'])
            with zipfile.ZipFile(root/'updates/update.zip') as archive:self.assertEqual(archive.namelist(),['pipeline/demo.py'])
            published=json.loads((root/'release.json').read_text('utf8'))
            self.assertIn('/v1.1.0/',published['archive']['url'])
