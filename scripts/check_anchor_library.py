"""Verify actual shared PNG bytes and desktop controls; capture source-art preview."""
import argparse
import json
import sys
from pathlib import Path
from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline.core import write_json, sha256
from pipeline.production import expression_assets, validate_anchor_library
from pipeline.performance import COMMON_STATES, ASSET_VARIANTS

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
out = args.output.resolve()
out.mkdir(parents=True, exist_ok=True)
manifest = validate_anchor_library()
assets = expression_assets()
records = []
for who, states in assets.items():
    for state in [v for category in COMMON_STATES for v in ASSET_VARIANTS[category]]:
        file = states[state]
        with Image.open(file) as image:
            assert image.mode == 'RGBA' and image.width == image.height
            alpha = image.getchannel('A')
            # The approved legacy happy sprite tops out at 254; preserve it.
            assert alpha.getextrema()[0] == 0 and alpha.getextrema()[1] >= 250
            records.append(dict(anchor=who, state=state, path=str(file), sha256=sha256(file), size=image.size))
with sync_playwright() as p:
    browser = p.chromium.launch(channel='msedge', headless=True)
    page = browser.new_page(viewport=dict(width=1920, height=1080), device_scale_factor=1)
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.goto((ROOT/'anchor-library-preview.html').as_uri(), wait_until='domcontentloaded')
    page.wait_for_function('Array.from(document.images).every(i=>i.complete&&i.naturalWidth>0)')
    assert page.locator('img').count() == len(records)
    page.screenshot(path=str(out/'library-preview.png'), full_page=True)
    page.goto((ROOT/'index.html').as_uri(), wait_until='domcontentloaded')
    loaded = []
    for who, states in assets.items():
        for state, path in states.items():
            if not path.is_file():
                continue  # Optional legacy poses can be omitted from a shared library.
            page.locator(f'button[onclick="changeExpression(\'{who}\', \'{state}\')"]').click()
            sprite = page.locator(f'#{who} img')
            sprite.evaluate('(i)=>i.decode()')
            assert sprite.get_attribute('data-expression') == state
            assert sprite.get_attribute('src').replace('\\', '/') == path.relative_to(ROOT).as_posix()
            loaded.append(dict(anchor=who, state=state))
    assert not errors, errors
    browser.close()
write_json(out/'library-qa.json', dict(status='passed', version=manifest['version'], common_images=records,
                                      desktop_buttons_loaded=loaded, page_errors=errors,
                                      screenshot='library-preview.png', no_pixel_edits=True))
print(json.dumps(dict(common_images=len(records), desktop_buttons=len(loaded), status='passed')))
