import tempfile
import unittest
from pathlib import Path
from pipeline.production import performance_events, expression_assets, resolve_media
from pipeline.core import sha256

class ProductionTests(unittest.TestCase):
    def test_sentence_focus_never_lands_inside_internal_silence(self):
        e=performance_events(dict(anchor='xiaoXu',text='继续关注。',scene=0),1,[(.1,.2),(.8,.9)])
        at=e[1]['at']
        self.assertTrue(.1 <= at < .2 or .8 <= at < .9, at)

    def test_reusing_video_file_preserves_each_sentences_trim(self):
        from pipeline.production import media_for_shot
        cached={'original.mp4':dict(path='run/media-01.mp4',offset=1,source_duration=40)}
        result=media_for_shot(dict(path='original.mp4',offset=20,kind='video'),cached)
        self.assertEqual(result['path'],'run/media-01.mp4')
        self.assertEqual(result['offset'],20)
        self.assertEqual(cached['original.mp4']['offset'],1)

    def test_every_sentence_changes_pose_inside_actual_speech_and_returns(self):
        for anchor in ['xiaoXu','xiaoHe']:
            for text in ['大家好，我是小序。','团队研发机器人软件。','这是一项后续任务安排。','我们下期再见。']:
                events=performance_events(dict(anchor=anchor,text=text,scene=0),4.0,[(.25,3.6)])
                self.assertEqual(events[0]['at'],0)
                self.assertTrue(.25 < events[1]['at'] < 3.6)
                self.assertNotEqual(events[0]['expression'],events[1]['expression'])
                self.assertEqual(events[-1]['expression'],events[0]['expression'])
                self.assertTrue(all(e['expression'] in expression_assets()[anchor] for e in events))

    def test_explicit_invalid_pose_or_timing_fails_before_render(self):
        line=dict(anchor='xiaoXu',text='科学消息。',scene=0)
        for value in [{'expression':'wave'}, {'focus_ratio':1.5}, {'action':'head-replacement'}]:
            with self.assertRaises(ValueError): performance_events(line,4,[(.2,3.5)],value)

    def test_short_utterance_still_has_bounded_events(self):
        e=performance_events(dict(anchor='xiaoHe',text='你好。',scene=-1),.3,[(.05,.25)])
        self.assertEqual(len(e),3)
        self.assertTrue(0 < e[1]['at'] < e[2]['at'] <= .3)

    def test_media_requires_origin_hash_and_archive_label(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'image.jpg';p.write_bytes(b'example')
            item=dict(path=p.name,kind='image',source_url='https://example.org/original',sha256=sha256(p),caption='官方原图',role='current',published_at='2026-11-07T08:00:00+08:00')
            self.assertEqual(resolve_media(item,Path(temp))['sha256'],sha256(p))
            for bad in [dict(item,sha256='0'*64),dict(item,source_url=''),dict(item,role='archive')]:
                with self.assertRaises(ValueError):resolve_media(bad,Path(temp))

    def test_unknown_date_archive_is_explicit_and_text_capture_cannot_be_a_visual(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'diagram.png';p.write_bytes(b'original diagram')
            item=dict(path=p.name,kind='image',source_url='https://example.org/original',sha256=sha256(p),
                      caption='官方图示 · 资料',role='archive',published_at=None,
                      media_date_precision='unknown',original_asset_first_publication_unknown=True,
                      media_date_note='官网图形资料首发日期未知，不冒称本期新功能画面。')
            self.assertIsNone(resolve_media(item,Path(temp))['published_at'])
            for bad in [dict(item,role='current'),dict(item,media_date_note=''),dict(item,role='source_capture')]:
                with self.assertRaises(ValueError):resolve_media(bad,Path(temp))

    def test_self_drawn_substitutes_fail_even_with_valid_origin_and_hash(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'image.png';p.write_bytes(b'source asset')
            item=dict(path=p.name,kind='image',source_url='https://example.org/original',sha256=sha256(p),caption='发布方原始图形资料',role='current',published_at='2026-11-09T08:00:00+08:00',asset_url='https://example.org/original.svg')
            self.assertEqual(resolve_media(item,Path(temp))['sha256'],sha256(p))
            for bad in [dict(item,asset_url='editorial://self-drawn'),dict(item,is_programmatic_editorial_art=True),dict(item,caption='编辑流程示意图，依据README整理')]:
                with self.assertRaises(ValueError):resolve_media(bad,Path(temp))

if __name__=='__main__':unittest.main()
