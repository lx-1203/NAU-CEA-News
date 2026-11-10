import sys,json,os
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from playwright.sync_api import sync_playwright
from pipeline.core import read_json,write_json
project=Path(__file__).resolve().parents[1]
config=read_json(project/'config/pipeline.json')
if (project/'runtime/browsers').exists():os.environ['PLAYWRIGHT_BROWSERS_PATH']=str(project/'runtime/browsers')
run=Path(sys.argv[1]).resolve();nav=read_json(run/'chapters.json');out=Path(sys.argv[2]) if len(sys.argv)>2 else run/'player-qa';out.mkdir(parents=True,exist_ok=True)
sections=len(nav['sections']);chapter_count=len(nav['chapters']);story_count=len(read_json(run/'edition.json')['stories'])
results={}
with sync_playwright() as pw:
 channel=config.get('browser_channel','msedge' if os.name=='nt' else None)
 b=pw.chromium.launch(headless=True,**({'channel':channel} if channel else {}));p=b.new_page(viewport={'width':1440,'height':1100})
 p.goto((run/'watch.html').as_uri());p.wait_for_function('document.querySelector("video").readyState>=1')
 duration=p.locator('video').evaluate('v=>v.duration');assert abs(duration-nav['duration'])<.35
 assert p.locator('.section-buttons button').count()==sections;assert p.locator('.chapter-list button').count()==chapter_count
 jumps=[]
 for cls,count in [('.section-buttons button',sections),('.chapter-list button',chapter_count)]:
  for i in range(count):
   button=p.locator(cls).nth(i);expected=float(button.get_attribute('data-start'));button.click()
   p.wait_for_function('t=>Math.abs(document.querySelector("video").currentTime-t)<.25',arg=expected)
   jumps.append(dict(kind=cls,index=i,expected=expected,actual=p.locator('video').evaluate('v=>v.currentTime')))
 seek=p.locator('.seek');seek.scroll_into_view_if_needed();box=seek.bounding_box();p.mouse.move(box['x']+box['width']*.90,box['y']+box['height']/2);p.mouse.down();p.mouse.move(box['x']+box['width']*.43,box['y']+box['height']/2,steps=8);p.mouse.up()
 p.wait_for_function('!document.querySelector("video").seeking')
 dragged=p.locator('video').evaluate('v=>v.currentTime');assert .38*duration<dragged<.48*duration
 seek.focus();before=float(seek.input_value());seek.press('ArrowRight');after=float(seek.input_value());assert after>before
 p.locator('video').evaluate('v=>v.muted=true');p.locator('.play').click();p.wait_for_function('!document.querySelector("video").paused');p.wait_for_timeout(400);p.locator('.play').click();assert p.locator('video').evaluate('v=>v.paused')
 p.locator('.mute').click();assert p.locator('video').evaluate('v=>!v.muted');p.locator('.mute').click();assert p.locator('video').evaluate('v=>v.muted')
 p.locator('.fullscreen').click();p.wait_for_function('document.fullscreenElement!==null');p.locator('.fullscreen').click();p.wait_for_function('document.fullscreenElement===null')
 p.locator('.news-player').screenshot(path=str(out/'desktop-player.png'))
 p.set_viewport_size({'width':390,'height':844});p.screenshot(path=str(out/'mobile-player.png'),full_page=True)
 assert p.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
 p.goto((run/'daily.html').as_uri());assert p.locator('article').count()==story_count
 p.wait_for_function('Array.from(document.querySelectorAll("article img")).every(i=>i.complete&&i.naturalWidth>0)')
 assert '原文截图' not in p.locator('footer').inner_text()
 results=dict(status='passed',run_dir=str(run),duration=duration,section_buttons=sections,chapters=chapter_count,jumps=jumps,real_mouse_drag_seconds=dragged,keyboard_before=before,keyboard_after=after,play_pause=True,mute=True,fullscreen=True,mobile_width=390,mobile_overflow=False,daily_articles=story_count,full_human_listening=False)
 b.close()
write_json(out/'player-qa.json',results);print(json.dumps(results,ensure_ascii=False))
