import unittest
import tempfile
import json
import hashlib
from pathlib import Path
from unittest.mock import patch

from pipeline.production import expression_assets, performance_events


class AnchorPerformanceTests(unittest.TestCase):
    def test_frequent_categories_map_three_distinct_assets(self):
        import pipeline.production as production
        manifest = production.read_json(production.ROOT/'config/anchor-library.json')
        for who in ['xiaoXu', 'xiaoHe']:
            for state in ['normal', 'happy', 'presenting', 'thinking']:
                variants = manifest['anchors'][who][state].get('variants', [])
                self.assertEqual(len(variants), 3, (who, state))
                self.assertEqual(len({v['sha256'] for v in variants}), 3)
                for v in variants:
                    self.assertEqual(expression_assets()[who][v['expression']], production.ROOT/v['path'])

    def test_each_intent_rotates_all_three_assets_for_each_anchor(self):
        from pipeline.performance import plan_performances, semantic_state
        for who in ['xiaoXu', 'xiaoHe']:
            for intent,state in [('neutral','normal'),('positive','happy'),('explain','presenting'),('analysis','thinking')]:
                lines = [dict(anchor=who, scene=0, text='这是一句播报。') for _ in range(12)]
                plans = plan_performances(lines, [], {str(i):dict(intent=intent) for i in range(12)})
                variants = {p['expression'] for p in plans if semantic_state(p['expression']) == state}
                self.assertEqual(variants, {state, state+'2', state+'3'}, (who,intent))
                for line,p in zip(lines,plans):
                    events = performance_events(line,2,[(.1,1.8)],p)
                    self.assertEqual(events[1]['expression'],p['expression'])
                    self.assertEqual(events[0]['expression'],p['base'])
                    self.assertEqual(events[-1]['expression'],p['base'])

    def test_explicit_variant_remains_frozen_and_audit_does_not_hide_category_repeats(self):
        from pipeline.performance import plan_performances, performance_audit
        line = dict(anchor='xiaoHe', scene=0, text='说明技术。')
        choice = plan_performances([line],[],{'0':dict(expression='thinking3',base='normal2')})[0]
        events = performance_events(line,2,[(.1,1.8)],choice)
        self.assertEqual(events[1]['expression'],'thinking3')
        self.assertEqual(events[0]['expression'],'normal2')
        shots=[dict(line,performance=dict(expression='presenting'+('' if i%3==0 else str(i%3+1)),action='hold')) for i in range(12)]
        audit=performance_audit(shots)['anchors']['xiaoHe']
        self.assertEqual(audit['states'],{'presenting':12})
        self.assertEqual(audit['longest_run'],12)
        self.assertEqual(len(audit['variants']),3)

    def test_missing_or_tampered_unused_state_is_rejected_before_audio(self):
        import pipeline.production as production
        from pipeline.performance import COMMON_STATES, ASSET_VARIANTS
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root/'config').mkdir()
            maps, manifest = {}, {'version': '1.0.0', 'anchors': {}}
            for who in ['xiaoXu', 'xiaoHe']:
                maps[who], manifest['anchors'][who] = {}, {}
                for state in COMMON_STATES:
                    variants = []
                    for expression in ASSET_VARIANTS[state]:
                        path = root/f'{who}-{expression}.png'
                        path.write_bytes((who+expression).encode())
                        maps[who][expression] = path
                        variants.append(dict(expression=expression, path=path.name, sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
                    manifest['anchors'][who][state] = dict(variants[0], variants=variants)
            (root/'config/anchor-library.json').write_text(json.dumps(manifest), encoding='utf8')
            with patch.object(production, 'ROOT', root):
                production.validate_anchor_library(maps)
                maps['xiaoHe']['surprised'].write_bytes(b'changed')
                with self.assertRaises(ValueError):
                    production.validate_anchor_library(maps)
                maps['xiaoHe']['surprised'].unlink()
                with self.assertRaises(ValueError):
                    production.validate_anchor_library(maps)

    def test_both_anchors_have_all_eight_common_states(self):
        common = {'normal', 'happy', 'surprised', 'thinking', 'serious', 'presenting', 'thumbsup', 'wave'}
        for anchor, assets in expression_assets().items():
            self.assertTrue(common <= assets.keys(), (anchor, common - assets.keys()))

    def test_matching_intent_uses_matching_state_for_both_anchors(self):
        from pipeline.performance import plan_performances
        for intent in ['neutral', 'explain', 'analysis', 'caution', 'positive', 'surprise', 'greet']:
            choices = []
            for anchor in ['xiaoXu', 'xiaoHe']:
                line = dict(anchor=anchor, text='本句重点。', scene=-1)
                p = plan_performances([line], [], {'0': {'intent': intent}})[0]
                choices.append(p['expression'])
            self.assertEqual(choices[0], choices[1], intent)

    def test_risks_and_funding_are_not_cheering_or_surprise(self):
        from pipeline.performance import plan_performances
        for text in ['该功能尚未正式开放。', '项目计划继续融资。', '金额翻倍，规模首次公开。', '修复可能导致失败的漏洞。']:
            for anchor in ['xiaoXu', 'xiaoHe']:
                p = plan_performances([dict(anchor=anchor, text=text, scene=0)], [], {})[0]
                self.assertNotIn(p['expression'], {'surprised', 'thumbsup', 'happy', 'wave', 'encourage'})
        p = plan_performances([dict(anchor='xiaoHe', text='实际效果仍需验证。', scene=0)], [], {})[0]
        self.assertEqual(p['expression'], 'serious')

    def test_repeat_control_stays_in_compatible_neutral_states(self):
        from pipeline.performance import plan_performances
        lines = [dict(anchor='xiaoHe', text='该接口提供检索功能。', scene=i // 4) for i in range(12)]
        plans = plan_performances(lines, [], {})
        self.assertEqual(plans, plan_performances(lines, [], {}))
        self.assertTrue({'normal', 'presenting'} <= {p['expression'] for p in plans})
        self.assertNotEqual(len({p['focus_ratio'] for p in plans}), 1)
        self.assertEqual({p['action'] for p in plans}, {'nod', 'hold'})
        for i in range(len(plans)-2):
            self.assertGreater(len({p['expression'] for p in plans[i:i+3]}), 1)

    def test_explicit_choice_is_retained_and_unknown_config_fails(self):
        from pipeline.performance import plan_performances
        lines = [dict(anchor='xiaoHe', text='介绍结果。', scene=0)]
        p = plan_performances(lines, [], {'0': dict(expression='thumbsup', action='hold', focus_ratio=.61)})[0]
        self.assertEqual((p['expression'], p['action'], p['focus_ratio']), ('thumbsup', 'hold', .61))
        for bad in [{'intent': 'nonsense'}, {'focus_ratio': float('nan')}, {'action': 'jump'}, {'base': 'missing'}]:
            with self.assertRaises(ValueError):
                performance_events(lines[0], 2, [(0.1, 1.8)], bad)
        for overrides in [{'2': {}}, {'bad': {}}, {'0': {'unknown': 1}}]:
            with self.assertRaises(ValueError):
                plan_performances(lines, [], overrides)

    def test_neutral_can_hold_and_returns_to_the_same_base(self):
        events = performance_events(dict(anchor='xiaoHe', text='平稳播报。', scene=0), 2, [(0.1, 1.8)],
                                    dict(expression='normal', base='normal', action='hold'))
        self.assertEqual({e['expression'] for e in events}, {'normal'})

    def test_audit_detects_repeated_old_pattern_without_forcing_emotions(self):
        from pipeline.performance import performance_audit
        shots = [dict(anchor='xiaoHe', scene=0, performance=dict(expression='encourage', intent='explain', action='nod')) for _ in range(12)]
        audit = performance_audit(shots)
        self.assertTrue(audit['warnings'])
        self.assertEqual(audit['anchors']['xiaoHe']['longest_run'], 12)


if __name__ == '__main__':
    unittest.main()
