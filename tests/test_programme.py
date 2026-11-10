import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from pipeline.programme import insert_interludes
from pipeline.navigation import build_navigation
from pipeline.opening import shift_timeline


class ProgrammeTests(unittest.TestCase):
    def test_silent_category_gaps_preserve_complete_speech_and_real_chapter_times(self):
        e=dict(date='2026-11-09',title='NAUCEA 新闻联播',stories=[dict(id=str(i),title='标题'+str(i),section=s) for i,s in enumerate(['headlines']*3+['technology']*3)])
        shots=[dict(scene=-1,start=0,end=2,duration=2),dict(scene=-1,start=2,end=8.5,duration=6.5,kind='overview',overview_section='headlines')]
        shots += [dict(scene=i,start=8.5+i*3,end=11.5+i*3,duration=3) for i in range(6)]
        cues=[dict(start=x['start'],end=x['end']) for x in shots]
        plan=dict(fps=30,total_frames=795,transitions=[dict(webm='one.webm',sha256='hash',frames=84)])
        with tempfile.TemporaryDirectory() as tmp,patch('pipeline.programme.render_interlude',return_value=Path('gap.mp4')):
            assembly,gaps,frozen=insert_interludes(shots,cues,[Path(str(i)+'.mp4') for i in range(len(shots))],e,{},plan,tmp)
        self.assertEqual(len(gaps),1)
        gap=gaps[0];self.assertAlmostEqual(gap['start'],17.5);self.assertAlmostEqual(gap['end'],20.9)
        self.assertEqual([a['cue'] for a in assembly if a['kind']=='speech'],list(range(8)))
        for s in shots:self.assertAlmostEqual(s['end']-s['start'],s['duration'])
        self.assertTrue(all(s['end']<=gap['start']+.0001 or s['start']>=gap['end']-.0001 for s in shots))
        t=shift_timeline(dict(fps=30,shots=shots,interludes=gaps,transitions=frozen),dict(duration_seconds=8,video='opening.mp4',video_sha256='hash'))
        nav=build_navigation(e,t)
        self.assertEqual(len(nav['sections']),2)
        self.assertAlmostEqual(nav['sections'][1]['start'],28.9)
        self.assertEqual([c['id'] for c in nav['chapters'] if c['id'].startswith('transition-')],['transition-technology'])
        self.assertEqual([c['id'] for c in nav['chapters'] if c['id'].startswith('overview-')],['overview-headlines'])

    def test_unexplained_gap_is_rejected(self):
        e=dict(date='2026-11-09',title='新闻',stories=[dict(id='a',title='标题',section='headlines')])
        with self.assertRaises(ValueError):build_navigation(e,dict(shots=[dict(scene=-1,start=0,end=1),dict(scene=0,start=4,end=5)]))
