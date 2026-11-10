import copy
import unittest
import json, tempfile
from pathlib import Path
from pipeline.core import sha256
from pipeline.opening import shift_timeline, load_opening
from pipeline.navigation import build_navigation


class OpeningTests(unittest.TestCase):
    def test_approved_opening_can_move_with_its_folder(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp)/'copy';folder.mkdir()
            for name in ['video.mp4','silent.mp4','CREDITS.txt']:(folder/name).write_bytes(name.encode())
            approval=dict(status='approved_for_use',placement='双主播演播室开场前',size=[1920,1080],fps=30,duration_seconds=8,video='video.mp4',silent_video='silent.mp4',credits_file='CREDITS.txt',video_sha256=sha256(folder/'video.mp4'),silent_video_sha256=sha256(folder/'silent.mp4'))
            (folder/'APPROVED.json').write_text(json.dumps(approval),encoding='utf8')
            result=load_opening({'opening':{'enabled':True,'approval':str(folder/'APPROVED.json')}})
            self.assertEqual(Path(result['video']),folder/'video.mp4')

    def test_prefix_offsets_subtitles_actions_sections_and_only_five_transitions(self):
        sections=['headlines','technology','applications','research','github','industry']
        e=dict(date='2026-11-09',title='每日新闻',stories=[dict(id=str(i),title=str(i),section=sections[i//3]) for i in range(18)])
        t=dict(fps=30,shots=[dict(scene=-1,start=0,end=2),*[dict(scene=i,start=2+i*3,end=5+i*3,performance_events=[dict(at=.2)]) for i in range(18)],dict(scene=-2,start=56,end=58)],transitions=dict(fps=30,total_frames=1740,transitions=[dict(cut_frame=x,from_frame=x-42) for x in [330,600,870,1140,1410]]))
        before=copy.deepcopy(t)
        shifted=shift_timeline(t,dict(duration_seconds=8,video='approved.mp4',video_sha256='hash'))
        self.assertEqual(t,before)
        self.assertEqual(shifted['shots'][1]['performance_events'],t['shots'][1]['performance_events'])
        self.assertEqual([x['cut_frame'] for x in shifted['transitions']['transitions']],[570,840,1110,1380,1650])
        nav=build_navigation(e,shifted)
        self.assertEqual(len(nav['chapters']),21)
        self.assertEqual(nav['chapters'][0]['id'],'opening')
        self.assertEqual(nav['chapters'][1]['start'],8)
        self.assertEqual(nav['duration'],66)
        self.assertEqual(nav['sections'][1]['start'],19)
        with self.assertRaises(ValueError):shift_timeline(shifted,dict(duration_seconds=8))
