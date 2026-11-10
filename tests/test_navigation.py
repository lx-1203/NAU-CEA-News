import copy
import json
import tempfile
import unittest
import subprocess
import hashlib
from pathlib import Path
from pipeline.core import validate_edition
from pipeline.navigation import build_navigation, export_navigation


SECTIONS = ['headlines', 'technology', 'applications', 'research', 'github', 'industry']

def edition():
    stories = []
    for i in range(18):
        stories.append(dict(id=f'news-{i}', event_id=f'event-{i}', section=SECTIONS[i//3],
            title=f'新闻{i}', source_url=f'https://example.com/{i}',
            published_at='2026-11-08T12:00:00+08:00', original_publication_date='2026-11-08',
            source_name='原始来源', verified=True, verification_note='已读取原文',
            summary='事实摘要', visual_labels=['新进展'], narration=['这是一条已核实消息。']))
    return dict(date='2026-11-09', title='每日资讯', section_schema_version=1, stories=stories)

def timeline():
    return dict(fps=30, shots=[dict(scene=-1, start=0, end=2),
        *[dict(scene=i, start=2+i*3, end=5+i*3) for i in range(18)],
        dict(scene=-2, start=56, end=58)])


class NavigationTests(unittest.TestCase):
    def test_eighteen_distinct_events_are_accepted(self):
        validate_edition(edition())

    def test_event_cannot_repeat_in_another_section(self):
        e=edition();e['stories'][4]['event_id']=e['stories'][0]['event_id']
        with self.assertRaisesRegex(ValueError, '事件重复'):validate_edition(e)

    def test_section_quota_and_order_are_checked(self):
        e=edition();e['stories'][3]['section']='headlines'
        with self.assertRaises(ValueError):validate_edition(e)
        e=edition();e['stories'][3],e['stories'][6]=e['stories'][6],e['stories'][3]
        with self.assertRaises(ValueError):validate_edition(e)

    def test_incomplete_section_requires_an_explanation(self):
        e=edition();e['stories'].pop()
        with self.assertRaisesRegex(ValueError, '缺额'):validate_edition(e)
        e['section_notes']={'industry':'已扩源，只有两条满足昨天首发条件。'}
        validate_edition(e)

    def test_times_come_from_actual_shots_not_equal_slices(self):
        t=timeline();t['shots'].insert(2,dict(scene=0,start=5,end=6))
        t['shots'][1]['end']=5
        for shot in t['shots'][3:]:shot['start']+=1;shot['end']+=1
        n=build_navigation(edition(),t)
        self.assertEqual(n['chapters'][1]['start'],2)
        self.assertEqual(n['chapters'][1]['end'],6)
        self.assertEqual(n['sections'][0]['end'],12)
        self.assertEqual(n['duration'],59)

    def test_rejects_gaps_missing_news_and_nonfinite_times(self):
        for change in ['gap','missing','nan']:
            t=timeline()
            if change=='gap':t['shots'][2]['start']+=.2
            if change=='missing':t['shots'][1]['scene']=1
            if change=='nan':t['shots'][2]['end']=float('nan')
            with self.assertRaises(ValueError):build_navigation(edition(),t)

    def test_legacy_eight_story_edition_still_has_navigation(self):
        e=edition();e.pop('section_schema_version');e['stories']=e['stories'][:8]
        for s in e['stories']:s.pop('section');s.pop('event_id')
        validate_edition(e)
        t=dict(fps=30,shots=timeline()['shots'][:9])
        n=build_navigation(e,t)
        self.assertEqual(len(n['chapters']),9)
        self.assertEqual(n['sections'][0]['title'],'新闻')

    def test_legacy_chinese_section_labels_are_still_compatible(self):
        e=edition();e.pop('section_schema_version');e['stories']=e['stories'][:8]
        for s,section in zip(e['stories'],['头条','必读',*['该知道']*4,*['顺手存']*2]):s['section']=section
        validate_edition(e)
        n=build_navigation(e,dict(shots=timeline()['shots'][:9]))
        self.assertEqual([s['title'] for s in n['sections']],['头条','必读','该知道','顺手存'])

    def test_exports_are_portable_and_text_is_not_executable(self):
        e=edition();e['stories'][0]['title']='</script><b>新闻</b>'
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp);export_navigation(e,timeline(),p)
            html=(p/'watch.html').read_text('utf8')
            self.assertNotIn('</script><b>新闻</b>',html)
            self.assertIn('news.mp4',html)
            self.assertTrue((p/'chapters.vtt').read_text('utf8').startswith('WEBVTT'))
            self.assertEqual((p/'chapters.ffmetadata').read_text('utf8').count('[CHAPTER]'),20)
            self.assertEqual(len(json.loads((p/'chapters.json').read_text('utf8'))['sections']),6)

    def test_browser_seeks_with_section_story_slider_and_keyboard(self):
        from playwright.sync_api import sync_playwright
        import imageio_ffmpeg
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)
            subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-v','error','-f','lavfi','-i',
                'color=c=0x193e3d:s=160x90:r=5:d=58','-c:v','libx264','-pix_fmt','yuv420p',str(p/'news.mp4')],check=True)
            export_navigation(edition(),timeline(),p)
            with sync_playwright() as pw:
                b=pw.chromium.launch(channel='msedge',headless=True)
                pg=b.new_page(viewport={'width':1280,'height':900})
                pg.goto((p/'watch.html').as_uri())
                pg.wait_for_function('window.newsPlayer && document.querySelector("video").readyState>=1')
                self.assertEqual(pg.locator('.section-buttons button').count(),6)
                self.assertEqual(pg.locator('.chapter-list button').count(),20)
                pg.locator('.section-buttons button').nth(2).click()
                self.assertAlmostEqual(pg.locator('video').evaluate('v=>v.currentTime'),20,places=2)
                pg.locator('.chapter-list button').nth(5).click()
                self.assertAlmostEqual(pg.locator('video').evaluate('v=>v.currentTime'),14,places=2)
                pg.locator('.seek').evaluate("e=>{e.value=30;e.dispatchEvent(new Event('input',{bubbles:true}));e.dispatchEvent(new Event('change',{bubbles:true}))}")
                self.assertAlmostEqual(pg.locator('video').evaluate('v=>v.currentTime'),30,places=2)
                pg.locator('.seek').focus();pg.keyboard.press('ArrowRight')
                self.assertGreater(pg.locator('video').evaluate('v=>v.currentTime'),30)
                self.assertFalse(pg.locator('video').evaluate('v=>v.controls'))
                pg.locator('.mute').click()
                self.assertTrue(pg.locator('video').evaluate('v=>v.muted'))
                pg.set_viewport_size({'width':390,'height':844})
                self.assertTrue(pg.evaluate('document.documentElement.scrollWidth<=innerWidth'))
                self.assertEqual(pg.locator('.section-buttons button').count(),6)
                b.close()

    def test_mp4_chapter_mux_preserves_audio_packets(self):
        import imageio_ffmpeg
        ff=imageio_ffmpeg.get_ffmpeg_exe()
        def run(args):return subprocess.run([ff,'-v','error',*map(str,args)],capture_output=True,check=True).stdout
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp);source=p/'original.mp4';dest=p/'chaptered.mp4'
            run(['-f','lavfi','-i','color=s=160x90:r=10:d=2','-f','lavfi','-i','sine=frequency=440:duration=2',
                 '-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac',source])
            e=edition();e['stories']=e['stories'][:1]
            t=dict(shots=[dict(scene=-1,start=0,end=.3),dict(scene=0,start=.3,end=1.7),dict(scene=-2,start=1.7,end=2)])
            export_navigation(e,t,p)
            run(['-i',source,'-i',p/'chapters.ffmetadata','-map','0:v','-map','0:a?','-map_metadata','0',
                 '-map_chapters','1','-c','copy','-movflags','+faststart',dest])
            original_audio=run(['-i',source,'-map','0:a','-c','copy','-f','data','-'])
            final_audio=run(['-i',dest,'-map','0:a','-c','copy','-f','data','-'])
            self.assertEqual(hashlib.sha256(original_audio).digest(),hashlib.sha256(final_audio).digest())
            metadata=run(['-i',dest,'-f','ffmetadata','-']).decode('utf8')
            self.assertEqual(metadata.count('[CHAPTER]'),3)
            run(['-i',dest,'-f','null','-'])
