import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from pipeline.storage import issue_paths, data_root, classify_file


class StorageTests(unittest.TestCase):
    def test_dates_and_categories_are_isolated_and_relocatable(self):
        with tempfile.TemporaryDirectory(prefix='news 空格 ') as temp:
            root=Path(temp)
            nine=issue_paths('2026-11-09',root=root,create=True)
            ten=issue_paths('2026-11-10',root=root,create=True)
            self.assertEqual(ten['editorial'],root/'data/issues/2026/2026-11-10/editorial')
            self.assertNotEqual(nine['images'],ten['images'])
            self.assertTrue(all(p.is_dir() for p in ten.values()))
            self.assertEqual(classify_file(Path('PHOTO.JPG')),'images')
            self.assertEqual(classify_file(Path('clip.mp4')),'videos')
            self.assertEqual(classify_file(Path('proof.html')),'evidence')

    def test_local_storage_and_environment_override(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'config').mkdir()
            (root/'config/storage.local.json').write_text(json.dumps({'data_root':'../news-data'}))
            with patch.dict('os.environ',{'NJAU_CEA_DATA_ROOT':''}):
                self.assertEqual(data_root(root),(root/'../news-data').resolve())
            with patch.dict('os.environ',{'NJAU_CEA_DATA_ROOT':str(root/'custom')}):
                self.assertEqual(data_root(root),root/'custom')

    def test_bad_or_normalized_dates_cannot_make_directories(self):
        with tempfile.TemporaryDirectory() as temp:
            for day in ['2026-2-01','2026-02-30','../escape','2026-11-10/../../out']:
                with self.assertRaises(ValueError):issue_paths(day,root=Path(temp),create=True)
            self.assertFalse((Path(temp)/'data').exists())
