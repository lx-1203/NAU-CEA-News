import tempfile
import unittest
from pathlib import Path
from PIL import Image


class LayoutTests(unittest.TestCase):
    def test_video_overlay_uses_picture_area_without_letterbox_bars(self):
        from pipeline.layout import contain_rect
        rect=contain_rect({'x':100,'y':200,'width':1200,'height':500},(1920,1080))
        x,y,w,h=rect
        self.assertEqual((y,h),(200,500))
        self.assertLessEqual(x+w,1300)
        self.assertAlmostEqual(w/h,1920/1080,places=2)

    def test_video_content_box_is_encodable_at_odd_css_size(self):
        from pipeline.layout import contain_rect
        x,y,w,h=contain_rect({'x':86.4,'y':248.4,'width':1209.6,'height':567},(960,540))
        self.assertEqual((w%2,h%2),(0,0))

    def test_invalid_crop_cannot_silently_remove_source(self):
        from pipeline.layout import validate_framing
        for crop in [[0,0,1,1.1], [.5,0,.4,1], [0,0,float('nan'),1]]:
            with self.assertRaises(ValueError):
                validate_framing({'crop':crop})

    def test_crop_preserves_source_pixels_and_original(self):
        from pipeline.layout import prepare_image
        with tempfile.TemporaryDirectory() as d:
            src,out=Path(d)/'source.png',Path(d)/'display.png'
            im=Image.new('RGB',(100,80),'white');im.putpixel((25,20),(7,23,41));im.save(src)
            before=src.read_bytes()
            prepare_image(src,out,{'crop':[.25,.25,.75,.75],'layout':'photo'})
            with Image.open(out) as result:
                self.assertEqual(result.size,(50,40))
                self.assertEqual(result.getpixel((0,0)),(7,23,41))
            self.assertEqual(src.read_bytes(),before)

    def test_fact_card_rejects_unreadable_or_empty_lists(self):
        from pipeline.layout import key_facts
        self.assertEqual(key_facts({'key_facts':['目标2028年末发射','任务仍属计划']}),['目标2028年末发射','任务仍属计划'])
        for facts in [[],['长'*23],['']]:
            with self.assertRaises(ValueError):key_facts({'key_facts':facts})
