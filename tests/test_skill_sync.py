import importlib.util,tempfile,unittest
from pathlib import Path
from pipeline.core import ROOT
spec=importlib.util.spec_from_file_location('skill_sync',ROOT/'scripts/install_agent_skill.py')
sync=importlib.util.module_from_spec(spec);spec.loader.exec_module(sync)


class SkillSyncTests(unittest.TestCase):
    def test_upgrade_preserves_user_edits_and_untracked_file_collisions(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'project';source=root/'skills/nau-cea-daily-video';source.mkdir(parents=True)
            (source/'SKILL.md').write_text('version one')
            home=Path(temp)/'assistant';sync.install(home,root)
            dest=home/'skills/nau-cea-daily-video'
            (dest/'references').mkdir();(dest/'references/new.md').write_text('user notes')
            (source/'references').mkdir();(source/'references/new.md').write_text('upstream reference')
            with self.assertRaisesRegex(ValueError,'Unmanaged'):sync.install(home,root)
            self.assertEqual((dest/'references/new.md').read_text(),'user notes')
            (dest/'references/new.md').unlink()
            (source/'SKILL.md').write_text('version two');sync.install(home,root)
            self.assertEqual((dest/'SKILL.md').read_text(),'version two')
            (dest/'SKILL.md').write_text('local edit')
            with self.assertRaisesRegex(ValueError,'local edits'):sync.install(home,root)
            self.assertEqual((dest/'SKILL.md').read_text(),'local edit')
