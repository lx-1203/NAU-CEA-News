import unittest,copy
from pipeline.core import ROOT,read_json
from scripts.check_current_programme import validate_current_programme


class CurrentProgrammeGateTests(unittest.TestCase):
    def fixture(self):
        return dict(title='NJAU-CEA 新闻联播',date='2026-11-09',stories=[dict(section='headlines',title='真实标题',narration=['一条消息。'])],section_overviews={'headlines':'头条关注一条消息。'})

    def test_daily_gate_rejects_missing_overview_instead_of_using_legacy_branch(self):
        e=self.fixture();e.pop('section_overviews')
        with self.assertRaises(ValueError):validate_current_programme(e,read_json(ROOT/'config/pipeline.json'))

    def test_current_brand_and_independent_category_policy_are_required(self):
        e=self.fixture();c=read_json(ROOT/'config/pipeline.json')
        self.assertEqual(validate_current_programme(e,c)['mode'],'independent_silent_interludes')
        e['title']='秾好科技'
        with self.assertRaises(ValueError):validate_current_programme(e,c)
        e=self.fixture();c['programme']['category_transition']='overlay'
        with self.assertRaises(ValueError):validate_current_programme(e,c)
