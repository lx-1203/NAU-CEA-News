import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pipeline.transitions import choose_variants, make_plan, compose_transitions


class TransitionTests(unittest.TestCase):
    def test_only_section_changes_receive_transitions_not_intro_outro_or_same_section(self):
        plan=make_plan(self.timeline(),self.library(),seed=2,sections=['headlines','technology'])
        self.assertEqual([x['cut_frame'] for x in plan['transitions']],[330])
        self.assertEqual(plan['boundary_scope'],'section')
        self.assertEqual(plan['transitions'][0]['from_section'],'headlines')
        self.assertEqual(plan['transitions'][0]['to_section'],'technology')
        self.assertEqual(make_plan(self.timeline(),self.library(),seed=2,sections=['headlines','headlines'])['transitions'],[])
        shots=[{'scene':-1,'start':0,'end':2}]
        for i in range(18):shots.append({'scene':i,'start':2+i*3,'end':5+i*3})
        shots.append({'scene':-2,'start':56,'end':59})
        sections=[s for s in ['headlines','technology','applications','research','github','industry'] for _ in range(3)]
        edition18=make_plan({'fps':30,'shots':shots},self.library(),seed=2,sections=sections)
        self.assertEqual([x['cut_frame'] for x in edition18['transitions']],[330,600,870,1140,1410])

    def test_fullscreen_transition_retains_real_broadcast_band_and_audio(self):
        import subprocess
        import imageio_ffmpeg
        import numpy as np
        ff=imageio_ffmpeg.get_ffmpeg_exe()
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'source.mp4';stinger=root/'stinger.webm';output=root/'output.mp4'
            subprocess.run([ff,'-v','error','-y','-f','lavfi','-i','color=c=blue:s=1920x1080:r=30:d=2',
                '-f','lavfi','-i','sine=frequency=440:sample_rate=48000:duration=2','-vf',
                'drawbox=x=0:y=886:w=iw:h=194:color=white:t=fill,drawbox=x=500:y=950:w=500:h=60:color=black:t=fill',
                '-c:v','libx264','-preset','ultrafast','-c:a','aac','-shortest',str(source)],check=True,capture_output=True)
            subprocess.run([ff,'-v','error','-y','-f','lavfi','-i','color=c=red:s=1920x1080:r=30:d=2',
                '-c:v','libvpx-vp9','-deadline','realtime','-cpu-used','8',str(stinger)],check=True,capture_output=True)
            library={'fps':30,'_root':str(root)}
            plan={'total_frames':60,'broadcast_band':{'x':0,'y':886,'width':1920,'height':194},
                  'transitions':[{'webm':stinger.name,'sha256':hashlib.sha256(stinger.read_bytes()).hexdigest(),'from_frame':0,'frames':60}]}
            receipt=compose_transitions(source,output,plan,library)
            reader=imageio_ffmpeg.read_frames(str(output),pix_fmt='rgb24');next(reader);pixels=np.frombuffer(next(reader),np.uint8).reshape(1080,1920,3);reader.close()
            self.assertGreater(pixels[200,200,0],220);self.assertLess(pixels[200,200,2],30)
            self.assertTrue(np.all(pixels[920,200]>220))
            self.assertTrue(np.all(pixels[970,700]<30))
            self.assertTrue(receipt['audio_packets_unchanged'])
            self.assertTrue(receipt['broadcast_band_preserved'])

    def library(self):
        return {'fps':30,'frames':84,'cut_frame':42,'width':1920,'height':1080,
                'items':[{'id':x,'webm':x+'.webm'} for x in ['a','b','c']]}

    def timeline(self):
        return {'fps':30,'shots':[
            {'scene':-1,'start':0,'end':4},
            {'scene':0,'start':4,'end':8},
            {'scene':0,'start':8,'end':11},
            {'scene':1,'start':11,'end':17},
            {'scene':-2,'start':17,'end':21}]}

    def test_seed_reproduces_assignment(self):
        self.assertEqual(choose_variants(['a','b','c'],23,seed=842),
                         choose_variants(['a','b','c'],23,seed=842))

    def test_bag_uses_every_item_and_never_repeats_adjacent(self):
        for seed in range(40):
            selected=choose_variants(['a','b','c'],99,seed=seed)['ids']
            self.assertTrue(all(a!=b for a,b in zip(selected,selected[1:])))
            for i in range(0,99,3):self.assertEqual(set(selected[i:i+3]),{'a','b','c'})

    def test_single_item_terminates_and_duplicate_ids_are_rejected(self):
        self.assertEqual(choose_variants(['a'],3,seed=0)['ids'],['a']*3)
        with self.assertRaises(ValueError):choose_variants(['a','a'],2,seed=0)
        with self.assertRaises(ValueError):choose_variants([],1,seed=0)

    def test_only_scene_boundaries_and_no_shift(self):
        plan=make_plan(self.timeline(),self.library(),seed=2)
        self.assertEqual([x['cut_frame'] for x in plan['transitions']],[120,330,510])
        self.assertEqual([x['from_frame'] for x in plan['transitions']],[78,288,468])
        self.assertEqual(plan['total_frames'],630)
        self.assertTrue(all(x['frames']==84 for x in plan['transitions']))

    def test_near_edge_or_overlapping_transitions_are_rejected(self):
        timeline=self.timeline();timeline['shots'][0]['end']=.5;timeline['shots'][1]['start']=.5
        with self.assertRaises(ValueError):make_plan(timeline,self.library(),seed=0)
        timeline=self.timeline();timeline['shots'][1]['end']=5;timeline['shots'][2].update(start=5,end=6);timeline['shots'][3]['start']=6
        with self.assertRaises(ValueError):make_plan(timeline,self.library(),seed=0)

    def test_composition_failure_keeps_source_and_existing_output(self):
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/'input.mp4';source.write_bytes(b'original-input')
            output=Path(folder)/'output.mp4';output.write_bytes(b'existing-output')
            with self.assertRaises(FileExistsError):
                compose_transitions(source,output,{'transitions':[]},self.library())
            self.assertEqual(source.read_bytes(),b'original-input')
            self.assertEqual(output.read_bytes(),b'existing-output')
            with self.assertRaises(ValueError):
                compose_transitions(source,source,{'transitions':[]},self.library())


if __name__=='__main__':unittest.main()
