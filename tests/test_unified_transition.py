import unittest
from PIL import Image
from pipeline.programme import compose_transition_frame


class UnifiedTransitionTests(unittest.TestCase):
    def setUp(self):
        self.card=Image.new('RGBA',(1920,1080),'green')
        self.previous=Image.new('RGB',(1920,1080),'red')
        self.following=Image.new('RGB',(1920,1080),'blue')

    def test_no_static_left_panel_survives_when_sweep_is_transparent(self):
        empty=Image.new('L',(1920,1080),0)
        opening=compose_transition_frame(self.card,empty,0,self.previous,self.following)
        closing=compose_transition_frame(self.card,empty,83,self.previous,self.following)
        self.assertEqual(opening.tobytes(),self.previous.tobytes())
        self.assertEqual(closing.tobytes(),self.following.tobytes())

    def test_one_shared_mask_controls_both_halves(self):
        mask=Image.new('L',(1920,1080),0)
        from PIL import ImageDraw
        ImageDraw.Draw(mask).rectangle((0,0,960,1079),fill=255)
        image=compose_transition_frame(self.card,mask,30,self.previous,self.following)
        self.assertEqual(image.getpixel((400,500)),(0,128,0))
        self.assertEqual(image.getpixel((1500,500)),(255,0,0))
        full=Image.new('L',(1920,1080),255)
        image=compose_transition_frame(self.card,full,42,self.previous,self.following)
        self.assertEqual(image.tobytes(),self.card.convert('RGB').tobytes())
