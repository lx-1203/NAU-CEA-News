"""Snapshot the existing broadcast set and cut with measured sentence audio."""
import html
import array
import json
import math
import os
import re
import shutil
import subprocess
import wave
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit
from PIL import Image, ImageDraw, ImageFont
from playwright.sync_api import sync_playwright
import imageio_ffmpeg
from .core import ROOT, TZ, coverage, read_json, write_json, validate_edition, make_cues, sha256
from .workbench import edition_lines, workbench_dependencies, prepare_workbench_audio, validate_audio_entries
from .production import production_plan, performance_events, expression_assets, media_for_shot
from .layout import key_facts, prepare_image, contain_rect
from .pacing import pace_for_render, pacing_summary
from .transitions import DEFAULT_LIBRARY, load_library, library_dependencies, make_plan as transition_plan, compose_transitions
from .navigation import export_navigation
from .bubble import capture_bubble, bubble_filter
from .opening import load_opening, opening_dependencies, prepend_opening, shift_timeline
from .programme import section_cards, draw_overview, insert_interludes

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
FONT = 'C:/Windows/Fonts/msyh.ttc'
PAD_AUDIO_FILTER = 'apad,alimiter=limit=0.89:level=false'


def apply_studio_branding(page,ending=False,day=''):
    """Reusable live/offline branding; fail rather than silently export old text."""
    page.evaluate('applyStudioBranding',dict(ending=ending,date=day))
    page.wait_for_function('''()=>{const image=document.getElementById('studioProgrammeLogo');return image.complete&&image.naturalWidth>0}''')
    if not page.locator('#studioProgrammeLogo').is_visible():
        raise ValueError('演播室大屏LOGO被样式隐藏，停止导出')
    receipt=page.evaluate('applyStudioBranding',dict(ending=ending,date=day))
    if receipt['source']!=page.locator('.branding-program-mark img').evaluate('e=>e.currentSrc'):
        raise ValueError('大屏与左下角节目LOGO不一致')
    return receipt


def news_time(story):
    value = datetime.fromisoformat(story['published_at']).astimezone(TZ)
    return value.strftime('%Y-%m-%d') if story.get('time_precision') == 'day' else value.strftime('%Y-%m-%d %H:%M +08:00')


def freeze_date(page, day):
    page.evaluate('''day=>{
        const stamp=document.querySelector('#subtitleDate');
        const freeze=()=>{if(stamp.textContent!==day)stamp.textContent=day;};
        freeze();
        new MutationObserver(freeze).observe(stamp,{childList:true,characterData:true,subtree:true});
    }''', day)


def voice_jitter(gate):
    """Deterministic 1–2 px whole-character motion, zero throughout silence."""
    return (f'2*sin(floor(t*30)*1.7)*({gate})',
            f'1.5*cos(floor(t*30)*2.3)*({gate})')


def particle_layer(x, y, w, h, fps=30):
    """Legacy transparent-layer interface retained for existing callers."""
    positions = [(.15,.23),(.84,.26),(.09,.45),(.89,.49),(.28,.09),(.73,.12),(.18,.66),(.83,.65)]
    boxes = ''.join(f',drawbox=x={x+round(w*px)}:y={y+round(h*py)}:w=7:h=7:color=0xd7e78a:t=fill:replace=1' for px,py in positions)
    return f'color=c=black@0.0:s=1920x1080:r={fps},format=rgba{boxes}'


def voice_particles(back, box, gate, fps=30):
    """Reuse the studio's eight yellow-green particles in offline exports."""
    x, y, w, h = box
    positions = [(.15,.23),(.84,.26),(.09,.45),(.89,.49),(.28,.09),(.73,.12),(.18,.66),(.83,.65)]
    graph = ''
    for i, (px, py) in enumerate(positions):
        phase = f'mod(t+{i*.107:.3f},0.85)/0.85'
        direction = -1 if px < .5 else 1
        dx = f'{x+round(w*px)}+{direction*14}*({phase})'
        dy = f'{y+round(h*py)}+8-30*({phase})'
        enable = f'({gate})*gte({phase},0.08)*lt({phase},0.82)'
        out = 'voicefx' if i == len(positions)-1 else f'particle{i}'
        graph += (f'color=c=0xd7e78a:s=6x6:r={fps},format=rgba[dot{i}];'
                  f"[{back}][dot{i}]overlay=x='{dx}':y='{dy}':enable='{enable}':eval=frame[{out}];")
        back = out
    return graph.rstrip(';')


def command(args, **kwargs):
    result = subprocess.run([str(x) for x in args], capture_output=True, **kwargs)
    if result.returncode: raise RuntimeError(result.stderr.decode('utf-8', errors='replace')[-6000:])
    return result


def infographic(story, path, number):
    image = Image.new('RGB', (1440, 780), '#FAF7EF')
    d = ImageDraw.Draw(image)
    def text(x, y, value, size=35, color='#1E4D3B'):
        d.text((x, y), value, font=ImageFont.truetype(FONT, size), fill=color)
    text(62, 40, f'NEWS {number:02d}  /  编辑信息图', 50)
    title = story['title']
    for i in range(0, len(title), 20): text(62, 112+(i//20)*74, title[i:i+20], 64)
    labels = story['visual_labels']
    count = len(labels)
    gap, left, top = 28, 62, 300
    width = (1316-gap*(count-1))//count
    for i, label in enumerate(labels):
        x = left+i*(width+gap)
        d.rounded_rectangle((x, top, x+width, top+242), 18, fill='#1E4D3B')
        text(x+24, top+10, f'0{i+1}', 32, '#D7E78A')
        # Label wraps to fit each box at full resolution.
        chars = max(3, int((width-42)/56))
        for j in range(0, len(label), chars): text(x+22, top+60+(j//chars)*60, label[j:j+chars], 56, '#FFFFFF')
    summary = story['summary']
    for i in range(0, min(len(summary), 52), 26): text(62, 552+(i//26)*58, summary[i:i+26], 48)
    text(62, 710, '编辑整理 · 非现场画面 · 原文来源见画面下方', 56, '#77776D')
    image.save(path)


def write_report(edition, run_dir):
    esc = html.escape
    cards = []
    for i, s in enumerate(edition['stories']):
        gallery = []
        displayed = set()
        for item in s.get('media',[]):
            if item['path'] in displayed: continue
            displayed.add(item['path'])
            src = esc(Path(item['path']).name, quote=True)
            element = f'<video controls preload="metadata" src="{src}"></video>' if item['kind']=='video' else f'<img src="{src}" alt="{esc(item["caption"],quote=True)}">'
            gallery.append(f'<figure>{element}<figcaption>{esc(item["caption"])} · <a href="{esc(item["source_url"],quote=True)}">素材来源</a></figcaption></figure>')
        visual = ''.join(gallery) or f'<img src="visual-{i:02d}.png" alt="{esc(s["title"])}">'
        cards.append(f'<article>{visual}<p class="meta">{i+1:02d} / {esc(s["source_name"])} · {esc(news_time(s))} · {esc(s.get("source_type", "媒体报道"))}</p><h2>{esc(s["title"])}</h2><p>{esc(s["summary"])}</p><p class="why">所以呢：{esc(s.get("why_it_matters", s["summary"]))}</p><a href="{esc(s.get("repository_url",s["source_url"]), quote=True)}">查看来源与原文</a></article>')
    start, _ = coverage(edition['date'])
    document = f'<!doctype html><html lang="zh-CN"><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{esc(edition["title"])} {edition["date"]}</title><style>body{{margin:0;background:#e5e4db;color:#1e4d3b;font:24px/1.7 "Microsoft YaHei",sans-serif}}main{{max-width:1080px;margin:auto;background:#faf7ef;padding:56px;box-sizing:border-box}}h1{{font-size:54px;line-height:1.3}}h2{{font-size:34px}}article{{border-top:2px solid #b9c1ae;padding:40px 0}}img{{width:100%;height:auto}}.meta,footer{{font-size:19px;color:#77776d}}.why{{padding:20px;background:#edf0df}}a{{color:#1e4d3b}}@media(max-width:700px){{body{{font-size:18px}}main{{padding:24px}}h1{{font-size:36px}}h2{{font-size:26px}}}}</style><main><header><p>NJAU-CEA / 校园科技联播 · {edition["date"]}</p><h1>{esc(edition["title"])}</h1><p>覆盖 {start:%Y-%m-%d} 全天（北京时间） · 共 {len(cards)} 条</p><p>三十秒读完：{"；".join(esc(s["title"]) for s in edition["stories"][:3])}。</p></header>{"".join(cards)}<footer>图片来源与用途见各条说明。新闻数量以已核实事实为准；语音与视频自动制作。纠错请注明日期及条目号。</footer></main></html>'
    document = document.replace('img{width:100%;height:auto}', 'img,video{width:100%;height:auto}figure{margin:24px 0}figcaption{font-size:18px;color:#77776d}')
    document = document.replace('图片来源与用途见各条说明。', '新闻素材采用原始照片、原始视频与图形资料，资料画面单独标注；来源及用途见各图说明。')
    document = document.replace('<header>', '<header><p><a href="watch.html">观看视频 · 按栏目和新闻跳转</a></p>', 1)
    (run_dir/'daily.html').write_text(document, encoding='utf-8')


def wav_duration(path):
    with wave.open(str(path), 'rb') as w: return w.getnframes()/w.getframerate()


def normalize_speech(path):
    """Measure each sentence, then apply fixed gain with a -3 dB true-peak ceiling."""
    analysis = command([FFMPEG,'-hide_banner','-i',path,'-af',
                        'loudnorm=I=-18:TP=-3:LRA=7:print_format=json','-f','null','-']).stderr.decode('utf8',errors='replace')
    stats = json.loads(analysis[analysis.rfind('{'):analysis.rfind('}')+1])
    loudness, true_peak = float(stats['input_i']), float(stats['input_tp'])
    if not math.isfinite(loudness) or not math.isfinite(true_peak): raise ValueError('配音静音或响度无法测量')
    gain = min(-18-loudness, -3-true_peak)
    if gain > 20: raise ValueError('配音过轻，拒绝异常放大噪声')
    original = path.with_name(path.stem+'-raw.wav')
    normalized = path.with_name(path.stem+'-normalized.wav')
    shutil.copy2(path, original)
    command([FFMPEG,'-v','error','-y','-i',original,'-af',f'volume={gain:.6f}dB','-ar','24000','-ac','1',normalized])
    with wave.open(str(path)) as a, wave.open(str(normalized)) as b:
        if a.getnframes()!=b.getnframes() or a.getframerate()!=b.getframerate(): raise ValueError('响度处理改变配音长度')
    normalized.replace(path)
    return dict(input_lufs=loudness, input_true_peak_db=true_peak, gain_db=round(gain,6),
                target_lufs=-18, ceiling_true_peak_db=-3, raw_file=original.name)


def speech_intervals(path, threshold=0.015):
    intervals = []
    with wave.open(str(path), 'rb') as w:
        if w.getsampwidth() != 2: raise ValueError('配音分析需要 16-bit PCM')
        rate, channels = w.getframerate(), w.getnchannels()
        chunk = max(1, rate//20)
        position = 0
        while data := w.readframes(chunk):
            samples = array.array('h', data)
            rms = math.sqrt(sum(v*v for v in samples)/len(samples))/32768
            start, end = position/rate, (position+len(samples)//channels)/rate
            if rms > threshold:
                if intervals and abs(intervals[-1][1]-start)<0.00001: intervals[-1]=(intervals[-1][0],end)
                else: intervals.append((start,end))
            position += len(samples)//channels
    return intervals


def timestamp(seconds):
    ms = round(seconds*1000)
    return f'{ms//3600000:02}:{ms//60000%60:02}:{ms//1000%60:02},{ms%1000:03}'


def prepare_news_ticker(page, headlines, run_dir):
    """Freeze a repeatable headline strip; final export scrolls on whole-film time."""
    page.evaluate('setNewsTicker', headlines)
    box = page.locator('.ticker>div').bounding_box()
    font_size = page.locator('.ticker span').evaluate('e=>parseFloat(getComputedStyle(e).fontSize)')
    font = ImageFont.truetype(FONT, round(font_size))
    cycle = '　　◆　　'.join(headlines)
    content_width = math.ceil(font.getlength(cycle))
    width, height = round(box['width']), math.ceil(box['height'])
    period = content_width + width + font.size * 4
    strip = Image.new('RGB', (period * (math.ceil(width / period) + 2), height), '#123e3c')
    draw = ImageDraw.Draw(strip)
    bounds = font.getbbox(cycle)
    baseline = (height - (bounds[3] - bounds[1])) / 2 - bounds[1]
    for start in range(0, strip.width, period):
        draw.text((start, baseline), cycle, font=font, fill='#e0e9df')
    asset = run_dir/'ticker-strip.png'
    strip.save(asset)
    return dict(headlines=headlines, image=asset.name, period_px=period, content_width_px=content_width,
                font_size_px=font.size, speed_px_per_second=60,
                box=dict(x=round(box['x']), y=round(box['y']), width=width, height=height))



def fit_news_ticker(receipt, duration):
    """Require enough factual copy for a readable single pass through the film."""
    if duration <= 0:
        raise ValueError('快讯片长必须大于零')
    speed = receipt['content_width_px'] / duration
    rate = speed / receipt['font_size_px']
    if not 2.2 <= rate <= 4.5:
        raise ValueError(f'快讯信息量不适合本期片长：{rate:.2f}全宽字/秒；请调整摘要，不能用过慢或过快滚动凑时长')
    receipt.update(speed_px_per_second=speed, film_seconds=duration,
                   full_width_characters_per_second=rate,
                   first_pass_complete_seconds=duration,
                   next_pass_enters_seconds=(receipt['period_px'] - receipt['box']['width']) / speed,
                   cycle_seconds=receipt['period_px'] / speed)
    return receipt


def overlay_news_ticker(source, target, receipt, run_dir, duration, fps=30):
    """A continuous ticker pass after transitions, preserving the existing audio."""
    box = receipt['box']
    exclusions=receipt.get('excluded_intervals',[])
    # Integer frame gates avoid a one-frame leak when rounded decimal seconds
    # lie a fraction above the exact frame timestamp (e.g. 2495/30).
    enable=":"+"enable='not("+'+'.join(f'gte(n,{round(a*fps)})*lt(n,{round(b*fps)})' for a,b in exclusions)+")'" if exclusions else ''
    graph = (f"[1:v]crop={box['width']}:{box['height']}:"
             f"x='mod(t*{receipt['speed_px_per_second']},{receipt['period_px']})':y=0[strip];"
             f"[0:v][strip]overlay={box['x']}:{box['y']}:shortest=1{enable},format=yuv420p[out]")
    command([FFMPEG,'-v','error','-y','-reinit_filter','0','-i',source,'-loop','1','-framerate',fps,
             '-i',run_dir/receipt['image'],'-filter_complex_threads','1','-filter_complex',graph,'-map','[out]',
             '-map','0:a?','-t',f'{duration:.6f}','-r',fps,'-c:v','libx264',
             '-preset','veryfast','-crf','20','-threads','2','-c:a','copy','-movflags','+faststart',target])


def render_edition(edition_path, run_dir, audio_manifest_path=None):
    from .bgm import BgmSession, settings
    if not settings(ROOT).get('enabled',True):
        return _render_edition(edition_path,run_dir,audio_manifest_path)
    edition=validate_edition(read_json(edition_path))
    with BgmSession(ROOT,edition['date']) as music:
        result=_render_edition(edition_path,run_dir,audio_manifest_path,bgm=music)
        music.seal_cache()
        # Seal output metadata and actual deletion before atomically counting use.
        receipt=Path(run_dir)/'bgm-receipt.json'
        value=read_json(receipt);value['cleanup']=music.cleanup_receipt
        write_json(receipt,value)
        result['files'][receipt.name]=sha256(receipt)
        result['bgm']['cache_audio_bytes_after']=music.cleanup_receipt['audio_bytes_after']
        write_json(Path(run_dir)/'manifest.json',result)
        music.commit(Path(run_dir)/'news.mp4')
    return result


def _render_edition(edition_path, run_dir, audio_manifest_path=None, bgm=None):
    edition = validate_edition(read_json(edition_path))
    from .date_guard import validate_issue_day
    validate_issue_day(edition['date'], archive=edition.get('archive_production',False))
    plan = production_plan(edition_path)
    config = read_json(ROOT/'config/pipeline.json')
    if config.get('portable_profile'):
        os.environ['PLAYWRIGHT_BROWSERS_PATH'] = str(ROOT/'runtime/browsers')
    fps = config['video']['fps']
    opening = load_opening(config)
    transition_library = (load_library(DEFAULT_LIBRARY)
                          if DEFAULT_LIBRARY.exists() and read_json(DEFAULT_LIBRARY).get('enabled') else None)
    run_dir.mkdir(parents=True, exist_ok=False)
    write_json(run_dir/'edition.json', edition)
    write_json(run_dir/'production-plan.json', plan)
    supplied_audio = Path(audio_manifest_path).resolve() if audio_manifest_path else ((edition_path.parent/edition['audio_manifest']).resolve() if edition.get('audio_manifest') else None)
    dependencies = [ROOT/'index.html', ROOT/'style.css', ROOT/'script.js', ROOT/'news-media.js', ROOT/'talking.js', ROOT/'voice-demo.js', ROOT/'config/pipeline.json', *sorted((ROOT/'pipeline').glob('*.py')), ROOT/'pipeline/speak.ps1', *sorted((ROOT/'assets/branding').glob('*.png')), *sorted((ROOT/'assets/characters/anchors/generated').glob('*.png')), *sorted((ROOT/'assets/characters/anchors/gestures-v2').glob('*.png'))]
    if transition_library: dependencies.extend(library_dependencies(transition_library))
    dependencies.extend(opening_dependencies(opening))
    # Shared branding can add a stylesheet and background video to index.html.
    dependencies.extend(p for p in ROOT.glob('*.css') if p not in dependencies)
    dependencies.extend(sorted((ROOT/'assets/branding').glob('*.mp4')))
    dependencies.extend(sorted((ROOT/'assets/branding').glob('*.svg')))
    dependencies.extend(sorted((ROOT/'assets/player').glob('news-player.*')))
    dependencies.append(edition_path.resolve())
    for name in ['config/bgm.json','config/bgm.local.json']:
        if (ROOT/name).is_file():dependencies.append(ROOT/name)
    if supplied_audio: dependencies.append(supplied_audio)
    dependencies.extend(workbench_dependencies(config))
    media_cache = {}
    for shot in plan['shots']:
        item = shot['media']
        if not item or item['path'] in media_cache: continue
        source = Path(item['path'])
        dependencies.append(source)
        target = run_dir/f'media-{len(media_cache):02d}{source.suffix}'
        shutil.copy2(source,target)
        local = dict(item,path=str(target),original_path=str(source))
        if item['kind']=='image':
            display = run_dir/f'display-{len(media_cache):02d}.png'
            prepare_image(source, display, item['framing'])
            local['display_path'] = str(display)
        if item['kind']=='video':
            command([FFMPEG,'-v','error','-i',target,'-f','null','-'])
            info = imageio_ffmpeg.read_frames(str(target));meta = next(info);info.close()
            if item['offset'] >= meta['duration']-.1: raise ValueError('视频素材起点超出原片')
            local['source_duration'] = meta['duration']
            poster = target.with_suffix('.jpg')
            command([FFMPEG,'-v','error','-y','-ss',str(item['offset']),'-i',target,'-frames:v','1',poster])
            local['poster'] = str(poster)
        media_cache[str(source)] = local
    source_hashes = {str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else str(p): sha256(p) for p in dependencies}
    report_edition = json.loads(json.dumps(edition))
    for i, s in enumerate(edition['stories']):
        if s.get('media'):
            report_edition['stories'][i]['media'] = [media_cache[str((edition_path.parent/m['path']).resolve())] for m in s['media']]
        else: infographic(s, run_dir/f'visual-{i:02d}.png', i+1)
    write_json(run_dir/'media-sources.json', list(media_cache.values()))
    write_report(report_edition, run_dir)
    lines = edition_lines(edition)
    provider = config.get('speech', {}).get('provider', 'system')
    if supplied_audio:
        # Existing edition contract: WAV paths are relative to edition.json.
        audio_manifest = validate_audio_entries(lines, read_json(supplied_audio), edition_path.parent)
        provider = 'external'
        write_json(run_dir/'audio-reuse.json',dict(manifest=str(supplied_audio),sha256=sha256(supplied_audio),note='复用已生成的完整配音清单；文本与WAV哈希逐句验证，默认每日仍按配置使用工作台'))
    elif provider == 'indextts2':
        audio_manifest = prepare_workbench_audio(lines, config, run_dir, edition['date'])
    elif provider == 'system':
        audio_manifest = {}
    else:
        raise ValueError(f'未知配音提供者: {provider}')
    if audio_manifest: write_json(run_dir/'audio-manifest.json', audio_manifest)
    audio_inputs = {str((edition_path.parent/entry['path']).resolve()): sha256(edition_path.parent/entry['path']) for entry in audio_manifest.values()}
    shots, clips, durations = [], [], []
    bubble_cache = {}
    overview_cards={c['id']:c for c in section_cards(edition)} if edition.get('section_overviews') else {}
    for key,card in overview_cards.items():draw_overview(card,run_dir/f'overview-{key}.png')
    broadcast_band = None
    with sync_playwright() as p:
        browser = p.chromium.launch(channel=config.get('browser_channel', 'msedge'), headless=True)
        page = browser.new_page(viewport={'width':1920, 'height':1080}, device_scale_factor=1)
        page.goto((ROOT/'index.html').as_uri())
        page.wait_for_function('typeof setNewsScene === "function" && typeof changeExpression === "function"')
        freeze_date(page, edition['date'])
        page.evaluate("document.body.classList.add('broadcast-mode')")
        page.add_style_tag(content='*{animation:none!important;transition:none!important}.ticker span{animation:none!important}.subtitle-text{font-size:64px!important}.news-scene h1{font-size:48px!important}.news-material-caption{font-size:26px!important}.news-board{display:none!important}.screen-content{padding-top:.2cqw!important}.screen-eyebrow{display:none}.screen-content>strong{font-size:2.2cqw!important;transform:none!important;line-height:1.15!important}.screen-tag{font-size:.8cqw!important}')
        page.evaluate('''date=>{
          document.querySelector('.live-badge').textContent='DAILY';
          document.querySelector('.screen-corner').textContent='DAILY NEWS';
          document.querySelector('#subtitleDate').textContent=date;
          document.querySelector('.topic-bar>span:nth-child(2)').textContent=date+' · 前一日科技资讯回顾';
        }''', edition['date'])
        ticker_receipt = prepare_news_ticker(page, [s.get('ticker_summary') or s['summary'] for s in edition['stories']], run_dir)
        page.add_style_tag(content='.ticker span{visibility:hidden!important}')
        for index, line in enumerate(lines):
            print(f'[{index+1}/{len(lines)}] {line["text"]}', flush=True)
            stem = f'cue-{index:03d}'
            text_path, wav = run_dir/f'{stem}.txt', run_dir/f'{stem}.wav'
            text_path.write_text(line['text'], encoding='utf-8')
            entry = audio_manifest.get(str(index))
            if entry:
                if entry['text'] != line['text']: raise ValueError('外部配音文本与字幕不一致')
                original = (edition_path.parent/entry['path']).resolve()
                if sha256(original) != audio_inputs[str(original)]: raise ValueError('剪辑前配音文件变化')
                command([FFMPEG,'-v','error','-y','-i',original,'-ar','24000','-ac','1',wav])
                voice = entry.get('voice', 'external')
            else:
                voice = config['voices'][line['anchor']]
                command([config['speech_shell'],'-NoProfile','-File',ROOT/'pipeline/speak.ps1','-TextFile',text_path,'-OutputFile',wav,'-Voice',voice])
            pacing = pace_for_render(wav, line, config.get('speech',{}).get('pacing',{}), fps=fps)
            normalization = normalize_speech(wav)
            if pacing: pacing['output_file_before_loudness'] = normalization['raw_file']
            raw_duration = wav_duration(wav)
            duration = math.ceil((raw_duration+0.22)*fps)/fps
            if line.get('kind')=='overview':duration=max(duration,float(config.get('programme',{}).get('overview_minimum_seconds',6.5)))
            durations.append(duration)
            scene = line['scene']
            selected = plan['shots'][index]['media']
            # File de-duplication must not collapse per-sentence trim offsets.
            media = media_for_shot(selected,media_cache)
            overview=line.get('kind')=='overview'
            page.locator('.news-side-label').evaluate("e=>e.style.visibility=''")
            if overview:
                card=overview_cards[line['overview_section']]
                visual=run_dir/f'overview-{card["id"]}.png'
                page.evaluate('''x=>{setNewsScene(true);document.querySelector('#newsAnchor').value=x.anchor;updateNewsAnchor();document.querySelector('#newsTitle').textContent=x.title;document.querySelector('#newsImage').hidden=false;document.querySelector('#newsVideo').hidden=true;document.querySelector('#newsEmpty').hidden=true;document.querySelector('#newsImage').src=x.image;}''',dict(anchor=line['anchor'],title='本期目录｜'+card['title'],image=visual.as_uri()))
                page.evaluate('applyNewsEditorialLayout',dict(facts=[f'{len(overview_cards)}栏目 · {len(edition["stories"])}条新闻'],layout='diagram',caption='本期目录 · '+card['title'],source='NJAU-CEA 新闻联播 · 前一日资讯回顾'))
                page.locator('.news-side-label').evaluate("e=>e.style.visibility='hidden'")
                page.locator('.topic-bar>span:first-child').evaluate("e=>e.textContent='目录'")
            elif scene >= 0:
                story = edition['stories'][scene]
                visual = Path(media.get('display_path',media.get('poster',media['path']))) if media else run_dir/f'visual-{scene:02d}.png'
                page.evaluate('''x=>{setNewsScene(true);document.querySelector('#newsAnchor').value=x.anchor;updateNewsAnchor();document.querySelector('#newsTitle').textContent=x.title;document.querySelector('#newsImage').hidden=false;document.querySelector('#newsVideo').hidden=true;document.querySelector('#newsEmpty').hidden=true;document.querySelector('#newsImage').src=x.image;document.querySelector('#newsMaterialCaption').textContent=x.source;document.querySelector('#newsCounter').textContent=x.counter;}''', dict(anchor=line['anchor'], title=story['title'], image=visual.as_uri(), source=media['caption'] if media else story['source_name']+' · '+news_time(story).split(' ')[0]+' · '+story.get('source_type','媒体报道'), counter=f'{scene+1:02d} / {len(edition["stories"]):02d}'))
            else:
                page.evaluate('setNewsScene(false)')
                apply_studio_branding(page,scene==-2,edition['date'])
                page.evaluate('''x=>{
                    document.querySelector('.news-board').innerHTML='<h2>本期资讯</h2>'+x.titles.map(t=>'<div><span></span></div>').join('');
                    document.querySelectorAll('.news-board div span').forEach((e,i)=>e.textContent=x.titles[i]);
                }''', dict(end=scene==-2, date=edition['date'], titles=[s['title'] for s in edition['stories'][:3]]))
            if scene >= 0:
                page.evaluate('applyNewsEditorialLayout', dict(
                    facts=key_facts(story), layout=media['framing']['layout'] if media else 'diagram',
                    caption=media.get('display_caption',media['caption']) if media else '编辑整理 · 非现场画面',
                    source=story['source_name']+' · '+news_time(story).split(' ')[0]+'｜配图：'+(media.get('credit') or media.get('source_name') or urlsplit(media['source_url']).hostname) if media else story['source_name']))
            page.evaluate('''x=>{changeExpression(x.anchor,x.anchor==='xiaoXu'?'normal':'happy');document.querySelector('#subtitleText').textContent=x.text;document.querySelector('#speakerName').textContent=x.anchor==='xiaoXu'?'小序':'小禾';}''', line)
            page.wait_for_function('Array.from(document.images).filter(e=>e.getBoundingClientRect().width>0).every(e=>e.complete && e.naturalWidth>0)')
            page.evaluate('document.fonts.ready')
            package=page.locator('.news-package').bounding_box()
            frame_box=page.locator('.tv-frame').bounding_box()
            current_band=dict(x=round(package['x']-frame_box['x']),y=round(package['y']-frame_box['y']),width=round(package['width']),height=round(package['height']))
            if broadcast_band is not None and current_band!=broadcast_band:raise ValueError('播报条位置随镜头变化，不能安全保留字幕层')
            broadcast_band=current_band
            for selector in ['#subtitleText', '#newsTitle' if scene>=0 or overview else '#studioProgrammeLogo', *(['.news-key-facts'] if scene>=0 else [])]:
                if not page.locator(selector).evaluate('e=>e.scrollWidth<=e.clientWidth+1'): raise ValueError(f'画面文字溢出: {selector}')
            screenshot = run_dir/f'{stem}.png'
            anchor = page.locator('#'+line['anchor'])
            box = anchor.locator('img').bounding_box()
            sprite_url = anchor.locator('img').get_attribute('src')
            sprite = ROOT/sprite_url
            bubble = None
            if scene >= 0:
                if scene not in bubble_cache:
                    bubble_cache[scene] = run_dir/f'bubble-{scene:02d}.png'
                    capture_bubble(page,bubble_cache[scene])
                bubble = bubble_cache[scene]
                page.locator('.news-side-label').evaluate("e=>e.style.visibility='hidden'")
            anchor.evaluate("e=>e.style.visibility='hidden'")
            page.locator('.tv-frame').screenshot(path=str(screenshot))
            anchor.evaluate("e=>e.style.visibility=''")
            if bubble:page.locator('.news-side-label').evaluate("e=>e.style.visibility=''")
            clip = run_dir/f'{stem}.mp4'
            intervals = speech_intervals(wav)
            if not intervals: raise ValueError(f'第 {index+1} 句配音无有效人声能量')
            events = performance_events(line,raw_duration,intervals,plan['shots'][index]['performance'])
            gate = '+'.join(f'gte(t,{a:.4f})*lt(t,{b:.4f})' for a,b in intervals) or '0'
            x,y,w,h = (round(box[k]) for k in ['x','y','width','height'])
            jitter_x, jitter_y = voice_jitter(gate)
            prefix = ''
            back = '0:v'
            foreground = ''
            desk = page.locator('.anchor-desk').bounding_box()
            if desk:
                dx,dy,dw,dh = (round(desk[k]) for k in ['x','y','width','height'])
                prefix = f'[0:v]split=2[back][front];[front]crop={dw}:{dh}:{dx}:{dy}[desk];'
                back = 'back'
                foreground = f'[beforeDesk][desk]overlay={dx}:{dy}[set];'
            inputs = ['-loop','1','-framerate',fps,'-i',screenshot]
            graph = prefix
            next_input = 1
            if bubble:
                inputs += ['-loop','1','-framerate',fps,'-i',bubble]
                graph += bubble_filter(next_input,sum(durations[:-1])).replace('{back}',back)
                back = 'withbubble'
                next_input += 1
            video_box = None
            if media and media['kind']=='video':
                if media['offset']+duration > media['source_duration']-.05: raise ValueError('所选原视频片段短于口播，请调整素材起点或更换素材')
                video_box = page.locator('#newsImage').bounding_box()
                with Image.open(visual) as poster_image:
                    mx,my,mw,mh = contain_rect(video_box, poster_image.size)
                video_box = dict(x=mx,y=my,width=mw,height=mh)
                inputs += ['-ss',str(media['offset']),'-i',media['path']]
                graph += f'[{next_input}:v]setpts=PTS-STARTPTS,scale={mw}:{mh}:force_original_aspect_ratio=decrease,pad={mw}:{mh}:(ow-iw)/2:(oh-ih)/2:color=0x0b202b,setsar=1[newsclip];[{back}][newsclip]overlay={mx}:{my}[withmedia];'
                back = 'withmedia'
                next_input += 1
            # Whole PNG swaps only; every event is explicit and reviewable.
            expressions = expression_assets()[line['anchor']]
            sprite_proof = []
            for event_index,event in enumerate(events):
                pose = expressions[event['expression']]
                inputs += ['-loop','1','-framerate',fps,'-i',pose]
                end = events[event_index+1]['at'] if event_index+1 < len(events) else duration
                enable = f'gte(t,{event["at"]:.6f})*lt(t,{end:.6f})'
                # One small nod/greeting arc, gated by actual speech; hold in silence.
                amplitude = 5 if event['action']=='nod' else 7 if event['action']=='greet' else 0
                elapsed = '+'.join(f'max(0,min(t,{b:.6f})-{max(a,event["at"]):.6f})' for a,b in intervals if b > event['at']) or '0'
                arc = f'{amplitude}*sin(min(({elapsed})/0.65,1)*PI)*({gate})'
                output = f'pose{event_index}'
                graph += f"[{next_input}:v]scale={w}:{h}:force_original_aspect_ratio=decrease:flags=neighbor,format=rgba,pad={w}:{h}:(ow-iw)/2:0:color=black@0[host{event_index}];[{back}][host{event_index}]overlay=x='{x}+({jitter_x})':y='{y}-({arc})+({jitter_y})':enable='{enable}':eval=frame[{output}];"
                back = output
                sprite_proof.append(dict(expression=event['expression'],path=str(pose.relative_to(ROOT)),sha256=sha256(pose)))
                next_input += 1
            graph += f'[{back}]null[beforeDesk];'+foreground if desk else f'[{back}]null[set];'
            graph += voice_particles('set', (x,y,w,h), gate, fps)+';[voicefx]format=yuv420p[out]'
            (run_dir/f'{stem}-filter.txt').write_text(graph, encoding='utf-8')
            command([FFMPEG,'-v','error','-y',*inputs,'-t',f'{duration:.6f}','-filter_complex_threads','1','-filter_complex_script',run_dir/f'{stem}-filter.txt','-map','[out]','-r',fps,'-c:v','libx264','-preset','veryfast','-crf','20','-an','-threads','2',clip])
            command([FFMPEG,'-v','error','-y','-i',wav,'-af',PAD_AUDIO_FILTER,'-t',f'{duration:.6f}','-ar','24000','-ac','1',run_dir/f'{stem}-padded.wav'])
            clips.append(clip)
            shots.append(dict(line, voice=voice, pacing=pacing, normalization=normalization, raw_duration=raw_duration, duration=duration, frame=screenshot.name, audio=wav.name, audio_sha256=sha256(wav), sprite=str(sprite.relative_to(ROOT)), sprite_sha256=sha256(sprite), speech_intervals=intervals, voice_effects=dict(jitter_px=[2,1.5],particles=8,gate='measured_speech_intervals',deterministic=True), bubble_effect=dict(asset=bubble.name,sha256=sha256(bubble),period_seconds=4.8,amplitude_px=7.296,clock_start=sum(durations[:-1])) if bubble else None, performance_events=events, pose_assets=sprite_proof, media=media, media_box=video_box))
        browser.close()
    if config.get('speech',{}).get('pacing',{}).get('enabled'):
        write_json(run_dir/'speech-pacing.json', pacing_summary(shots,config['speech']['pacing']))
    cues = make_cues([x['text'] for x in lines], durations)
    for shot, cue in zip(shots, cues): shot.update(start=cue['start'], end=cue['end'])
    (run_dir/'subtitles.srt').write_text('\n\n'.join(f'{i+1}\n{timestamp(c["start"])} --> {timestamp(c["end"])}\n{c["text"]}' for i,c in enumerate(cues))+'\n', encoding='utf-8-sig')
    write_json(run_dir/'timeline.json', dict(fps=fps, shots=shots))
    assembly=[dict(path=p,cue=i,kind='speech',seconds=durations[i]) for i,p in enumerate(clips)]
    interludes=[];inserted_plan=None
    independent_transitions=bool(edition.get('section_overviews') and transition_library)
    if independent_transitions:
        initial_plan=transition_plan(dict(fps=fps,shots=shots),transition_library,seed=edition.get('transition_seed'),sections=[s['section'] for s in edition['stories']])
        assembly,interludes,inserted_plan=insert_interludes(shots,cues,clips,edition,transition_library,initial_plan,run_dir)
        write_json(run_dir/'timeline.json',dict(fps=fps,shots=shots,interludes=interludes,transitions=inserted_plan))
        write_json(run_dir/'transition-plan.json',inserted_plan)
        (run_dir/'subtitles.srt').write_text('\n\n'.join(f'{i+1}\n{timestamp(c["start"])} --> {timestamp(c["end"])}\n{c["text"]}' for i,c in enumerate(cues))+'\n',encoding='utf-8-sig')
    (run_dir/'concat.txt').write_text('\n'.join(f"file '{p['path'].name}'" for p in assembly), encoding='utf-8')
    with wave.open(str(run_dir/'narration.wav'), 'wb') as combined:
        combined.setparams((1,2,24000,0,'NONE','not compressed'))
        for item in assembly:
            if item['kind']=='silence':combined.writeframes(b'\0'*(round(item['seconds']*24000)*2))
            else:
                with wave.open(str(run_dir/f'cue-{item["cue"]:03d}-padded.wav'), 'rb') as part:
                    combined.writeframes(part.readframes(part.getnframes()))
    video = run_dir/'news.mp4'
    command([FFMPEG,'-v','error','-y','-f','concat','-safe','0','-i',run_dir/'concat.txt','-i',run_dir/'narration.wav','-map','0:v:0','-map','1:a:0','-c:v','copy','-c:a','aac','-ar','48000','-ac','2','-b:a','160k','-movflags','+faststart',video])
    transition_receipt = None
    if independent_transitions:
        transition_receipt=dict(mode='inserted_silent_interludes',plan=inserted_plan,narration_wavs_preserved=True,body_speech_during_interludes=False,interludes=interludes)
        write_json(run_dir/'transition-receipt.json',transition_receipt)
    elif transition_library:
        frozen_plan = transition_plan(dict(fps=fps, shots=shots), transition_library,seed=edition.get('transition_seed'),broadcast_band=broadcast_band,sections=[s.get('section','news') for s in edition['stories']])
        write_json(run_dir/'transition-plan.json', frozen_plan)
        transition_receipt = compose_transitions(video, run_dir/'news-with-transitions.mp4', frozen_plan, transition_library)
        write_json(run_dir/'transition-receipt.json', transition_receipt)
        video.rename(run_dir/'news-before-transitions.mp4')
        (run_dir/'news-with-transitions.mp4').rename(video)
        transition_receipt.update(video=str(video), source=str(run_dir/'news-before-transitions.mp4'))
        write_json(run_dir/'transition-receipt.json', transition_receipt)
        write_json(run_dir/'timeline.json', dict(fps=fps, shots=shots, transitions=frozen_plan))
    fit_news_ticker(ticker_receipt, cues[-1]['end'])
    if interludes:ticker_receipt['excluded_intervals']=[[x['start'],x['end']] for x in interludes]
    overlay_news_ticker(video, run_dir/'news-with-ticker.mp4', ticker_receipt, run_dir, cues[-1]['end'], fps)
    video.rename(run_dir/'news-before-ticker.mp4')
    (run_dir/'news-with-ticker.mp4').rename(video)
    write_json(run_dir/'ticker-receipt.json', ticker_receipt)
    opening_receipt = None
    if opening:
        opening_receipt = prepend_opening(video,run_dir/'news-with-opening.mp4',opening)
        no_bgm_receipt = prepend_opening(video,run_dir/'news-no-bgm.mp4',opening,silent=True)
        video.rename(run_dir/'news-body.mp4')
        (run_dir/'news-with-opening.mp4').rename(video)
        opening_receipt['body'] = str(run_dir/'news-body.mp4')
        no_bgm_receipt['body'] = str(run_dir/'news-body.mp4')
        opening_receipt['no_bgm'] = no_bgm_receipt
        write_json(run_dir/'opening-receipt.json',opening_receipt)
        shifted = shift_timeline(read_json(run_dir/'timeline.json'),opening)
        shots = shifted['shots']
        write_json(run_dir/'timeline.json',shifted)
        if transition_receipt:
            transition_receipt['body_plan'] = transition_receipt['plan']
            transition_receipt['plan'] = shifted['transitions']
            if interludes:
                transition_receipt['body_interludes']=transition_receipt['interludes']
                transition_receipt['interludes']=shifted['interludes']
            transition_receipt['opening_offset_seconds'] = opening['duration_seconds']
            write_json(run_dir/'transition-plan.json',shifted['transitions'])
            write_json(run_dir/'transition-receipt.json',transition_receipt)
        for cue in cues:
            cue['start'] += opening['duration_seconds']
            cue['end'] += opening['duration_seconds']
        (run_dir/'subtitles.srt').write_text('\n\n'.join(f'{i+1}\n{timestamp(c["start"])} --> {timestamp(c["end"])}\n{c["text"]}' for i,c in enumerate(cues))+'\n',encoding='utf-8-sig')
        (run_dir/'narration.wav').rename(run_dir/'narration-body.wav')
        with wave.open(str(run_dir/'narration-body.wav'),'rb') as source, wave.open(str(run_dir/'narration.wav'),'wb') as target:
            target.setparams(source.getparams())
            target.writeframes(b'\0'*(round(opening['duration_seconds']*source.getframerate())*source.getnchannels()*source.getsampwidth()))
            target.writeframes(source.readframes(source.getnframes()))
        shutil.copy2(opening['credits_file'],run_dir/'CREDITS.txt')
    # Chapter timestamps come from final measured speech, never equal story slices.
    if config.get('navigation', {}).get('enabled', True):
        export_navigation(edition, read_json(run_dir/'timeline.json'), run_dir)
        if config.get('navigation', {}).get('embed_mp4_chapters', True):
            chaptered = run_dir/'news-with-chapters.mp4'
            command([FFMPEG,'-v','error','-y','-i',video,'-i',run_dir/'chapters.ffmetadata',
                     '-map','0:v','-map','0:a?','-map_metadata','0','-map_chapters','1',
                     '-c','copy','-movflags','+faststart',chaptered])
            video.rename(run_dir/'news-before-chapters.mp4')
            chaptered.rename(video)
            if opening:
                command([FFMPEG,'-v','error','-y','-i',run_dir/'news-no-bgm.mp4','-i',run_dir/'chapters.ffmetadata',
                         '-map','0:v','-map','0:a?','-map_metadata','0','-map_chapters','1','-c','copy',run_dir/'news-no-bgm-with-chapters.mp4'])
                (run_dir/'news-no-bgm-with-chapters.mp4').replace(run_dir/'news-no-bgm.mp4')
    if bgm:
        # This remix input stays usable after disposable downloaded music is gone.
        if not (run_dir/'news-no-bgm.mp4').exists():shutil.copy2(video,run_dir/'news-no-bgm.mp4')
        bgm.mix(video,run_dir/'news-with-bgm.mp4',read_json(run_dir/'timeline.json'))
        (run_dir/'news-with-bgm.mp4').replace(video)
    # A complete decode is required before advancing the latest pointer.
    command([FFMPEG,'-v','error','-i',video,'-f','null','-'])
    info = imageio_ffmpeg.read_frames(str(video))
    metadata = next(info)
    info.close()
    if tuple(metadata['size']) != (1920,1080) or abs(metadata['fps']-fps)>0.01: raise ValueError('成片尺寸或帧率不符')
    if abs(metadata['duration']-cues[-1]['end']) > 0.35: raise ValueError('成片与字幕时长不一致')
    volume = command([FFMPEG,'-hide_banner','-i',video,'-vn','-af','volumedetect','-f','null','-']).stderr.decode('utf-8', errors='replace')
    (run_dir/'audio-analysis.txt').write_text(volume, encoding='utf-8')
    match = re.search(r'max_volume: ([-\w.]+) dB', volume)
    peak = float(match.group(1)) if match else float('-inf')
    if not -45 < peak < 0: raise ValueError(f'音频峰值异常: {peak}')
    # Contact sheet is generated from actual output, not source PNGs.
    frames = []
    for i, scene in enumerate([-1, *range(len(edition['stories'])), -2]):
        candidates = [s for s in shots if s['scene']==scene]
        for sample in [candidates[0]['start']+0.1, (candidates[0]['start']+candidates[-1]['end'])/2, candidates[-1]['end']-0.15]:
            frame = run_dir/f'qa-{len(frames):02d}.png'
            command([FFMPEG,'-v','error','-y','-ss',str(max(0,sample)),'-i',video,'-frames:v','1',frame])
            frames.append(frame)
    sheet = Image.new('RGB', (1440, math.ceil(len(frames)/3)*270), 'white')
    for i, frame in enumerate(frames):
        with Image.open(frame) as im: sheet.paste(im.resize((480,270)), ((i%3)*480,(i//3)*270))
    sheet.save(run_dir/'contact-sheet.jpg', quality=92)
    from .task_finish import register_intermediates
    disposable=[*clips,*[item['path'] for item in assembly],*[run_dir/f'cue-{i:03d}-padded.wav' for i in range(len(lines))]]
    disposable.extend(run_dir/name for name in ['news-before-transitions.mp4','news-before-ticker.mp4','news-body.mp4'])
    # These working copies remain usable until finalization has copied and
    # verified current; only that later lifecycle step may retire them.
    disposable.extend(run_dir/name for name in ['news.mp4','watch.html','daily.html'])
    register_intermediates(run_dir,edition['date'],disposable)
    files = {p.name:sha256(p) for p in run_dir.iterdir() if p.is_file()}
    current_hashes = {name:sha256(ROOT/name) for name in source_hashes}
    if current_hashes != source_hashes: raise ValueError('渲染期间源码变化，请按新源码重新渲染')
    if any(sha256(path) != digest for path,digest in audio_inputs.items()): raise ValueError('渲染期间配音源文件变化')
    if bgm:
        music_receipt=dict(bgm.receipt,status='validated',video_sha256=sha256(video))
        write_json(run_dir/'bgm-receipt.json',music_receipt)
        files['bgm-receipt.json']=sha256(run_dir/'bgm-receipt.json')
    manifest = dict(status='rendered', editorial_status='reviewed', publication_status='not_published', date=edition['date'], created_at=datetime.now(TZ).isoformat(), metadata=metadata, total_seconds=cues[-1]['end'], peak_db=peak, speech_provider=provider, voices=sorted({s['voice'] for s in shots}), source_hashes=source_hashes, audio_inputs=audio_inputs, files=files, checks=dict(full_decode=True, dimensions=True, fps=True, duration=True, peak=True), limitations=['固定机位、逐句切素材；新闻原视频静音，只保留主播口播', '句中表情动作按语义和发声区间比例安排，未做逐字强制对齐；整图姿态切换，不是骨骼动画或嘴型同步', '音色采用项目选定参考音频，合成音频按实际时长重排字幕与镜头', '未进行人工完整试听；自动音量测量不代表发音自然度验收'])
    if transition_receipt:
        manifest['transitions'] = dict(count=len(transition_receipt['plan']['transitions']),
                                       seed=transition_receipt['plan']['seed'],
                                       plan='transition-plan.json', audio_packets_unchanged=not independent_transitions,
                                       library_sha256=sha256(DEFAULT_LIBRARY))
    if opening_receipt:
        manifest['opening'] = opening_receipt
    if bgm:
        manifest['bgm']=dict(receipt='bgm-receipt.json',sha256=bgm.selection['track']['sha256'],
                             cycle=bgm.selection['cycle'],catalog_version=bgm.selection['catalog_version'])
    write_json(run_dir/'manifest.json', manifest)
    return manifest
