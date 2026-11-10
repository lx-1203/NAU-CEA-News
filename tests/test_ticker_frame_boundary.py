import subprocess,tempfile,unittest
from pathlib import Path
from PIL import Image
from pipeline.render import FFMPEG,overlay_news_ticker


class TickerFrameBoundaryTests(unittest.TestCase):
    def test_rounded_seconds_do_not_leak_ticker_on_first_transition_frame(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source=root/'source.mp4';output=root/'out.mp4'
            subprocess.run([FFMPEG,'-v','error','-f','lavfi','-i','color=c=black:s=160x90:r=30:d=0.233333333','-frames:v','7','-c:v','libx264','-pix_fmt','yuv420p',str(source)],check=True,capture_output=True)
            Image.new('RGB',(160,6),'red').save(root/'strip.png')
            receipt=dict(box=dict(x=0,y=80,width=160,height=6),image='strip.png',speed_px_per_second=0,period_px=160,excluded_intervals=[[.066667,.166667]])
            overlay_news_ticker(source,output,receipt,root,7/30)
            raw=subprocess.run([FFMPEG,'-v','error','-i',str(output),'-vf','crop=160:6:0:80','-pix_fmt','rgb24','-f','rawvideo','-'],check=True,capture_output=True).stdout
            stride=160*6*3;self.assertEqual(len(raw),stride*7)
            for frame in range(7):
                red=raw[frame*stride+(2*160+80)*3]
                self.assertLess(red,15) if 2<=frame<5 else self.assertGreater(red,220)
