import tempfile
import unittest
from pathlib import Path
from PIL import Image
from pipeline.programme import draw_category_card


class CategoryDiagonalTests(unittest.TestCase):
    def test_full_diagonal_and_right_side_stay_uncovered(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);background=root/'campus.png';plate=root/'plate.png'
            Image.new('RGB',(640,360),'#80a0b0').save(background)
            draw_category_card(dict(title='科技要闻',titles=['第一条消息','第二条消息','第三条消息']),plate,background)
            with Image.open(plate) as image:
                self.assertEqual(image.size,(1920,1080))
                for y in [0,200,540,850,1079]:
                    centre=round(1262-250*y/1080)
                    for dx in [-12,0,12]:self.assertEqual(image.getpixel((centre+dx,y)),(215,231,138,255))
                    self.assertEqual(image.getpixel((centre+35,y))[3],0)
                # Old rectangular mask removed the bottom of the diagonal.
                self.assertEqual(image.getpixel((1012,1079)),(215,231,138,255))
                # Neutral campus: the reveal must increase left→right.
                samples=[image.getpixel((x,200))[:3] for x in [50,500,850,1100]]
                luma=[sum(p) for p in samples]
                self.assertEqual(luma,sorted(luma))
                self.assertGreater(luma[-1]-luma[0],100)
