import unittest
from pathlib import Path
from playwright.sync_api import sync_playwright
from pipeline.core import ROOT

class StudioBrandingTests(unittest.TestCase):
 def test_branding_survives_render_freeze_scene_roundtrip_and_outro(self):
  from pipeline.render import apply_studio_branding
  with sync_playwright() as pw:
   browser=pw.chromium.launch(channel='msedge',headless=True,args=['--disable-gpu'])
   page=browser.new_page(viewport={'width':1920,'height':1080})
   page.goto((ROOT/'index.html').as_uri())
   page.wait_for_function('typeof setNewsScene === "function"')
   page.evaluate("document.body.classList.add('broadcast-mode')")
   page.add_style_tag(content='*{animation:none!important;transition:none!important}')
   for ending in [False,True]:
    page.evaluate('setNewsScene',True);page.evaluate('setNewsScene',False)
    receipt=apply_studio_branding(page,ending,'2026-11-09')
    self.assertEqual(receipt['phase'],'outro' if ending else 'intro')
    self.assertTrue(receipt['source'].endswith('/assets/branding/njau-cea-news-raster.png'))
    self.assertEqual(receipt['source'],page.locator('.branding-program-mark img').evaluate('e=>e.currentSrc'))
    screen=page.locator('.branding-screen').bounding_box()
    self.assertGreater(receipt['width']/screen['width'],.90)
    self.assertTrue(page.locator('#studioProgrammeLogo').is_visible())
    self.assertFalse(page.locator('.screen-content>strong').is_visible())
   page.evaluate('setNewsScene',True)
   self.assertFalse(page.locator('#studioProgrammeLogo').is_visible())
   self.assertTrue(page.locator('.branding-program-mark img').is_visible())
   page.evaluate('setNewsScene',False)
   page.emulate_media(reduced_motion='reduce')
   self.assertTrue(page.locator('#studioProgrammeLogo').is_visible())
   page.add_style_tag(content='#studioProgrammeLogo{display:none!important}')
   with self.assertRaisesRegex(ValueError,'大屏LOGO被样式隐藏'):
    apply_studio_branding(page)
   browser.close()
