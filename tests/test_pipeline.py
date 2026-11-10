import unittest
import tempfile
import wave
import struct
from pathlib import Path
from unittest.mock import patch
from datetime import datetime
from pipeline.core import validate_edition, normalize_items, coverage, make_cues


def story():
    return dict(id='one', title='AI 工具发布', published_at='2026-11-07T09:00:00+08:00', original_publication_date='2026-11-07',
                source_url='https://example.com/one', source_name='来源', verified=True,
                verification_note='读取原文核对日期和事实', summary='发布了新的工具。',
                narration=['今天介绍一款工具。'], visual_labels=['输入', '处理', '输出'])


class PipelineTests(unittest.TestCase):
    def test_36kr_space_separated_timestamp(self):
        from pipeline.collect import parse_date
        self.assertEqual(parse_date('2026-11-07 09:30:00  +0800'), '2026-11-07T09:30:00+08:00')

    def edition(self):
        return dict(date='2026-11-08', title='秾好，科技！', stories=[story()])

    def test_day_uses_shanghai_midnight(self):
        start, end = coverage('2026-11-08')
        self.assertEqual(start.isoformat(), '2026-11-07T00:00:00+08:00')
        self.assertEqual((end-start).total_seconds(), 86400)

    def test_rejects_unverified_and_old_news(self):
        for field, value in [('verified', False), ('published_at', '2026-10-22T00:00:00+08:00')]:
            edition = self.edition()
            edition['stories'][0][field] = value
            with self.assertRaises(ValueError): validate_edition(edition)

    def test_rejects_old_original_in_new_repost(self):
        edition = self.edition()
        edition['stories'][0]['original_publication_date'] = '2026-10-22'
        with self.assertRaises(ValueError): validate_edition(edition)

    def test_speech_motion_stops_in_silence(self):
        from pipeline.render import speech_intervals
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'test.wav'
            with wave.open(str(path),'wb') as w:
                w.setparams((1,2,24000,0,'NONE','not compressed'))
                w.writeframes(struct.pack('<'+'h'*24000, *([0]*6000+[10000]*6000+[0]*12000)))
            self.assertEqual(speech_intervals(path), [(0.25, 0.5)])

    def test_failed_render_preserves_last_success_and_releases_lock(self):
        import json
        import pipeline.run as runner
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root/'data').mkdir(parents=True)
            pointer = root/'data/latest.json'
            pointer.write_text('{"video":"keep-existing.mp4"}', encoding='utf8')
            edition = root/'edition.json'
            edition.write_text(json.dumps({'date':'2026-11-08'}), encoding='utf8')
            from contextlib import nullcontext
            with patch.object(runner, 'ROOT', root), patch('pipeline.updates.ensure_current',return_value={'status':'current'}), patch('pipeline.updates.production_guard',return_value=nullcontext()), patch('sys.argv', ['run','render','--edition',str(edition),'--archive']), patch('pipeline.render.render_edition', side_effect=RuntimeError('test failure')):
                with self.assertRaisesRegex(RuntimeError, 'test failure'): runner.main()
            self.assertEqual(json.loads(pointer.read_text())['video'],'keep-existing.mp4')
            self.assertFalse((root/'data/.render.lock').exists())
            self.assertTrue((root/'data/issues/2026/2026-11-08/last-failure.json').exists())

    def test_requires_timezone_and_evidence(self):
        for field, value in [('published_at', '2026-11-07T09:00:00'), ('verification_note', ''), ('visual_labels', [])]:
            edition = self.edition()
            edition['stories'][0][field] = value
            with self.assertRaises(ValueError): validate_edition(edition)

    def test_rejects_narration_string(self):
        edition = self.edition()
        edition['stories'][0]['narration'] = '这不是逐句数组。'
        with self.assertRaises(ValueError): validate_edition(edition)

    def test_display_converts_to_shanghai(self):
        from pipeline.render import news_time
        s = dict(story(), published_at='2026-11-06T20:00:00-05:00')
        self.assertEqual(news_time(s), '2026-11-07 09:00 +08:00')

    def test_export_date_cannot_be_overwritten_by_live_clock(self):
        from pipeline.render import freeze_date
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(channel='msedge',headless=True)
            page = browser.new_page()
            page.set_content('<time id="subtitleDate">实时日期</time>')
            freeze_date(page, '2026-11-08')
            page.evaluate("document.querySelector('#subtitleDate').textContent='11月08日 06:13'")
            self.assertEqual(page.locator('#subtitleDate').inner_text(),'2026-11-08')
            browser.close()

    def test_rendered_speech_particles_have_visible_alpha(self):
        import io
        import subprocess
        from PIL import Image
        from pipeline.render import particle_layer, FFMPEG
        output = subprocess.run([FFMPEG,'-v','error','-f','lavfi','-i',particle_layer(0,0,100,100),'-frames:v','1','-f','image2pipe','-vcodec','png','-'],capture_output=True,check=True)
        with Image.open(io.BytesIO(output.stdout)) as image:
            self.assertEqual(image.getpixel((17,25))[3],255)
            self.assertEqual(image.getpixel((0,0))[3],0)

    def test_canonical_links_deduplicate(self):
        items = [dict(story(), source_url='https://example.com/one?f=rss'), story()]
        self.assertEqual(len(normalize_items(items)), 1)

    def test_valid_edition_and_cue_boundaries(self):
        validate_edition(self.edition())
        cues = make_cues(['甲', '乙'], [1.23, 2.45])
        self.assertEqual(cues[1]['start'], cues[0]['end'])
        self.assertAlmostEqual(cues[-1]['end'], 3.68)
        with self.assertRaises(ValueError): make_cues(['甲'], [0])


if __name__ == '__main__': unittest.main()
