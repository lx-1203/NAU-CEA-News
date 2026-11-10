import unittest
from PIL import Image,ImageDraw
from pipeline.programme import context_footer


class TransitionFooterTests(unittest.TestCase):
    def test_guide_replaces_spoken_caption_without_erasing_programme_frame(self):
        source=Image.new('RGB',(1920,1080),'#ddddee');draw=ImageDraw.Draw(source)
        draw.rectangle((0,886,325,1079),fill='#236649')
        draw.rectangle((326,886,1919,937),fill='#adc7d0')
        draw.rectangle((326,938,1919,1037),fill='#ff00ff')
        draw.rectangle((326,1038,1919,1079),fill='#174b40')
        result=context_footer(source,'科技要闻')
        for point in [(150,970),(1000,910),(1000,1060),(1000,500)]:self.assertEqual(result.getpixel(point),source.getpixel(point))
        self.assertNotIn((255,0,255),list(result.crop((326,938,1920,1038)).getdata()))
        pixels=list(result.crop((470,943,1800,1037)).getdata())
        self.assertGreater(sum(1 for p in pixels if max(p)<110),1000)
