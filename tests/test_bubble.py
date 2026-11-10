import tempfile,unittest
from pathlib import Path
from PIL import Image
from playwright.sync_api import sync_playwright
from pipeline.core import ROOT
from pipeline.bubble import capture_bubble,bubble_filter

class BubbleTests(unittest.TestCase):
 def test_transparent_capture_has_no_studio_rectangle_and_header_matches_anchor(self):
  with tempfile.TemporaryDirectory() as temp,sync_playwright() as pw:
   browser=pw.chromium.launch(channel='msedge',headless=True)
   page=browser.new_page(viewport={'width':1920,'height':1080})
   page.goto((ROOT/'index.html').as_uri());page.wait_for_function('typeof applyNewsEditorialLayout === "function"')
   page.evaluate("document.body.classList.add('broadcast-mode');document.querySelector('#newsAnchor').value='xiaoHe';setNewsScene(true);applyNewsEditorialLayout({facts:['原始事实。'],layout:'photo',caption:'现场照片',source:'原始来源'})")
   self.assertEqual(page.locator('.news-side-label>b').inner_text(),'小禾划重点')
   path=Path(temp)/'bubble.png';capture_bubble(page,path)
   with Image.open(path) as im:
    self.assertEqual(im.mode,'RGBA');self.assertEqual(im.getpixel((100,100))[3],0)
    self.assertGreater(im.getpixel((1550,300))[3],0)
    self.assertLess(im.getchannel('A').getbbox()[0],1600)
   self.assertNotEqual(page.locator('#newsTitle').evaluate('e=>getComputedStyle(e).visibility'),'hidden')
   page.evaluate("applyNewsEditorialLayout({facts:['甲'.repeat(22),'乙'.repeat(22),'丙'.repeat(22)],layout:'photo',caption:'现场照片',source:'原始来源'})")
   bubble=page.locator('.news-side-label').bounding_box();host=page.locator('#xiaoHe').bounding_box()
   self.assertLess(bubble['y']+bubble['height']+27,host['y']-10)
   browser.close()
 def test_bubble_motion_uses_exact_input_and_continuous_time(self):
  graph=bubble_filter(2,12.5)
  self.assertIn('[2:v]',graph);self.assertIn('t+12.500000',graph);self.assertIn('/4.8',graph)
