"""Development sample: unchanged approved sentence WAVs and the new pose planner."""
import argparse
import html
import math
import subprocess
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline.core import read_json, write_json, sha256
from pipeline.production import expression_assets, performance_events, validate_anchor_library
from pipeline.performance import plan_performances
from pipeline.workbench import edition_lines
from pipeline.render import FFMPEG, voice_jitter, voice_particles

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--current', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
current, out = args.current.resolve(), args.output.resolve()
out.mkdir(parents=True, exist_ok=True)
library_version = validate_anchor_library()['version']
edition, timeline = read_json(current/'edition.json'), read_json(current/'timeline.json')
lines = edition_lines(edition)
plans = plan_performances(lines, edition['stories'], edition.get('performance'))
selected = []
for who in ['xiaoXu', 'xiaoHe']:
    for intent in ['neutral', 'explain', 'analysis', 'caution']:
        index = next(i for i, (line, plan) in enumerate(zip(lines, plans))
                     if line['anchor'] == who and line['scene'] >= 0 and plan['intent'] == intent)
        selected.append(index)
assets = expression_assets()
labels = dict(neutral='平稳播报', explain='讲解功能', analysis='分析与条件', caution='限制与风险')
clips, receipts = [], []
with sync_playwright() as p:
    browser = p.chromium.launch(channel='msedge', headless=True)
    page = browser.new_page(viewport=dict(width=1920, height=1080), device_scale_factor=1)
    for number, index in enumerate(selected):
        line, choice, old = lines[index], plans[index], timeline['shots'][index]
        assert line['text'] == old['text']
        wav = (current/old['audio']).resolve()
        assert sha256(wav) == old['audio_sha256']
        duration = old['duration']
        intervals = old['speech_intervals']
        events = performance_events(line, old['raw_duration'], intervals, choice)
        name = '小序' if line['anchor'] == 'xiaoXu' else '小禾'
        title = edition['stories'][line['scene']]['title']
        page.set_content(f'''<!doctype html><meta charset="utf-8"><style>
            *{{box-sizing:border-box}}body{{margin:0;background:#e9eee6;color:#203d35;font-family:Microsoft YaHei,sans-serif}}
            header{{background:#173d36;color:#fffdf0;padding:35px 70px;font-size:32px}}
            main{{padding:100px 100px}}small{{font-size:28px;color:#5b7566}}h1{{font-size:65px;width:1000px;line-height:1.5;text-wrap:balance}}
            h2{{font-size:36px;color:#507b56}}footer{{position:absolute;bottom:50px;left:100px;font-size:28px;color:#496854}}
            .stage{{position:absolute;right:100px;top:300px;width:650px;height:650px;border-bottom:3px solid #acbd9f}}
            .name{{position:absolute;right:100px;top:230px;width:650px;text-align:center;font-size:38px}}</style>
            <header>NJAU-CEA · 双主播表演样片</header><main><small>{html.escape(title)}</small>
            <h2>{number+1:02d} / 08　{labels[choice['intent']]}</h2><h1>{html.escape(line['text'])}</h1></main>
            <div class="name">{name}</div><div class="stage"></div><footer>共同基础表演库 · 保留原配音</footer>''')
        page.evaluate('document.fonts.ready')
        background = out/f'sample-{number:02d}.png'
        page.screenshot(path=str(background))
        inputs = ['-loop', '1', '-framerate', '30', '-i', str(background)]
        graph, back = '', '0:v'
        gate = '+'.join(f'gte(t,{a:.6f})*lt(t,{b:.6f})' for a,b in intervals)
        jx, jy = voice_jitter(gate)
        for n,event in enumerate(events):
            inputs.extend(['-loop','1','-framerate','30','-i',str(assets[line['anchor']][event['expression']])])
            end = events[n+1]['at'] if n+1<len(events) else duration
            amplitude = 5 if event['action']=='nod' else 7 if event['action']=='greet' else 0
            elapsed = '+'.join(f'max(0,min(t,{b:.6f})-{max(a,event["at"]):.6f})' for a,b in intervals if b>event['at']) or '0'
            arc = f'{amplitude}*sin(min(({elapsed})/0.65,1)*PI)*({gate})'
            graph += f"[{n+1}:v]scale=650:650:flags=neighbor,format=rgba[h{n}];[{back}][h{n}]overlay=x='1170+({jx})':y='300-({arc})+({jy})':enable='gte(t,{event['at']:.6f})*lt(t,{end:.6f})':eval=frame[v{n}];"
            back = f'v{n}'
        graph += voice_particles(back,(1170,300,650,650),gate,'30')+';[voicefx]format=yuv420p[out]'
        graphfile = out/f'sample-{number:02d}-filter.txt'
        graphfile.write_text(graph,encoding='utf8')
        inputs.extend(['-i',str(wav)])
        clip = out/f'sample-{number:02d}.mp4'
        subprocess.run([FFMPEG,'-v','error','-y',*inputs,'-t',str(duration),'-filter_complex_threads','1',
                        '-filter_complex_script',str(graphfile),'-map','[out]','-map','4:a:0',
                        '-af','apad','-ar','24000','-ac','1','-r','30','-c:v','libx264','-preset','veryfast',
                        '-crf','20','-c:a','aac','-b:a','128k','-threads','2',str(clip)],check=True)
        clips.append(clip)
        receipts.append(dict(cue=index, text=line['text'], anchor=line['anchor'], performance=choice,
                             events=events, duration=duration, wav=str(wav), audio_sha256=sha256(wav)))
    browser.close()
concat = out/'concat.txt'
concat.write_text(''.join("file '"+p.as_posix()+"'\n" for p in clips),encoding='utf8')
video = out/f'anchor-performance-sample-v{library_version}.mp4'
subprocess.run([FFMPEG,'-v','error','-y','-f','concat','-safe','0','-i',str(concat),'-c','copy','-movflags','+faststart',str(video)],check=True)
subprocess.run([FFMPEG,'-v','error','-i',str(video),'-f','null','-'],check=True)
write_json(out/'sample-receipt.json',dict(status='development_sample_verified_decode',version=library_version,
           video=str(video),video_sha256=sha256(video),shots=receipts,total_seconds=sum(r['duration'] for r in receipts),
           full_news_rerendered=False,new_tts_generated=False))
print(video)
