"""Attach the approved reusable outro and its edition-specific credits."""
import copy
import math
from pathlib import Path

from .bgm import _ffmpeg
from .core import ROOT, read_json, sha256
from .storage import issue_paths
from .updates import _no_links


def credit_cards(template, producer, only=False):
    producer = producer.strip()
    if not producer or len(producer) > 24 or any(ord(c) < 32 for c in producer):
        raise ValueError('片尾制作人署名需为 1–24 个可显示字符')
    cards = copy.deepcopy(template)
    if len(cards) != 3 or cards[0]['label'] != '制片人':
        raise ValueError('片尾署名模板结构错误')
    names = [producer] if only else list(dict.fromkeys(['星迹', 'Codex', producer]))
    label = ' · '.join(names)
    cards[0]['lines'] = [label] if len(label) <= 13 or len(names) == 1 else [' · '.join(names[:-1]), names[-1]]
    return cards


def approved_outro(config, root=ROOT):
    options = config.get('outro', {})
    if not options.get('enabled'):
        return None
    package = (Path(root) / options['package']).absolute()
    _no_links(package)
    manifest_path = package / 'MANIFEST.json'
    _no_links(manifest_path)
    manifest = read_json(manifest_path)
    dependencies = [manifest_path]

    def member(name):
        path = package / name
        _no_links(path)
        path = path.resolve()
        if not path.is_relative_to(package.resolve()):
            raise ValueError('片尾素材超出批准目录')
        record = manifest['files'][name]
        if path.stat().st_size != record['bytes'] or sha256(path) != record['sha256']:
            raise ValueError(f'片尾素材校验失败：{name}')
        dependencies.append(path)
        return path

    current = read_json(member('CURRENT.json'))
    template = read_json(member(current['credits_config']))
    music = read_json(member(current['music_config']))
    duration = float(current['duration_seconds'])
    if (current['version'] != manifest['version'] or template['version'] != current['version']
            or not math.isfinite(duration) or not 5 <= duration <= 60
            or abs(music['placement_seconds'] + music['duration_seconds'] - duration) > .01):
        raise ValueError('片尾版本或时长与批准清单不符')
    cards = template['cards']
    if any(not 0 <= card['start'] < card['end'] <= duration for card in cards):
        raise ValueError('片尾署名出现时间无效')
    lines = read_json(member('timeline.json'))['lines']
    if len(lines) != 2 or any(not 0 <= x['start'] < x['end'] <= music['placement_seconds'] for x in lines):
        raise ValueError('固定片尾双主播口播时间无效')
    return dict(version=current['version'], duration=duration, cards=cards,
                video=member(music['default_video']), voice=member('source/outro-voice.wav'),
                plate_html=member('source/credits.html'), lines=lines, music=music,
                package=package.resolve(), dependencies=dependencies)


def load_outro(config, day, root=ROOT):
    outro = approved_outro(config, root)
    if outro is None:
        return None
    credits_path = issue_paths(day, root=root)['tasks'] / 'credits.json'
    _no_links(credits_path)
    if not credits_path.is_file():
        raise ValueError(f'{day} 需要当期制作人署名：{credits_path}')
    credits = read_json(credits_path)
    if credits.get('edition_date') != day or credits.get('confirmed_by_user') is not True:
        raise ValueError('片尾制作人须经用户确认且刊期一致')
    outro['dependencies'].append(credits_path)
    outro['cards'] = credit_cards(outro['cards'], credits['producer'], credits.get('producer_only') is True)
    return outro


def append_outro_timeline(timeline, outro):
    if timeline.get('outro') or any(s['scene'] == -2 for s in timeline['shots']):
        raise ValueError('固定片尾会替换旧告别段')
    start = timeline['shots'][-1]['end']
    end = round(start + outro['duration'], 6)
    lines = [dict(text=line['text'], anchor=line['anchor'],
                  start=round(start + line['start'], 6), end=round(start + line['end'], 6))
             for line in outro['lines']]
    tail = dict(start=start, end=end, title='片尾与署名', version=outro['version'], lines=lines)
    timeline['outro'] = tail
    return tail


def render_outro(outro, run, fps, browser_channel='msedge'):
    """Reuse the approved video and credit card layout at the programme frame rate."""
    from playwright.sync_api import sync_playwright

    inputs = ['-i', outro['video']]
    graph = [f'[0:v]fps={fps},setpts=PTS-STARTPTS[base]']
    previous = 'base'
    plates = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel=browser_channel, headless=True)
        page = browser.new_page(viewport={'width': 1000, 'height': 424})
        page.goto(outro['plate_html'].as_uri())
        for index, card in enumerate(outro['cards'], start=1):
            page.evaluate('card => window.showCredit(card)', card)
            page.evaluate('document.fonts.ready')
            longest = max(map(len, card['lines']))
            page.locator('.name').evaluate('(node, size) => node.style.fontSize = size + "px"',
                                           max(30, min(67, 780 // longest)))
            fits = page.evaluate('''() => {const main=document.querySelector('main');
              return main.scrollWidth <= main.clientWidth && main.scrollHeight <= main.clientHeight}''')
            if not fits:
                raise ValueError('片尾署名超出卡片尺寸')
            plate = run / f'outro-credit-{index}.png'
            page.screenshot(path=str(plate), omit_background=True)
            plates.append(plate)
            inputs.extend(['-framerate', fps, '-i', plate])
            fade = f",fade=t=out:st={card['end']-0.6:.6f}:d=0.6:alpha=1" if index == len(outro['cards']) else ''
            graph.append(f"[{index}:v]format=rgba,loop=-1:1:0,settb=1/{fps},setpts=N,"
                         f"fade=t=in:st={card['start']}:d=0.45:alpha=1{fade}[card{index}]")
            graph.append(f"[{previous}][card{index}]overlay=460:444:shortest=1:"
                         f"enable='between(t,{card['start']},{card['end']})'[layer{index}]")
            previous = f'layer{index}'
        browser.close()
    target = run / 'outro-with-credits.mp4'
    _ffmpeg(['-nostdin', *inputs, '-filter_complex_threads', '1', '-filter_complex', ';'.join(graph),
             '-map', f'[{previous}]', '-map', '0:a:0', '-c:a', 'copy', '-t', outro['duration'],
             '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '18', '-pix_fmt', 'yuv420p',
             '-threads', '2', target])
    return target, plates


def join_outro(body, tail, tail_audio, target, start, duration, playlist):
    """Keep encoded video frames, with an audio splice aligned to the body end."""
    names = [Path(path).name for path in (body, tail)]
    if not all(name.replace('-', '').replace('.', '').isalnum() for name in names):
        raise ValueError('片尾拼接文件名无效')
    playlist.write_text(f"ffconcat version 1.0\nfile '{names[0]}'\nduration {start:.9f}\n"
                        f"file '{names[1]}'\nduration {duration:.9f}\n", encoding='ascii')
    graph = []
    for index, length in [(1, start), (2, duration)]:
        graph.append(f'[{index}:a]aformat=sample_rates=48000:channel_layouts=stereo,'
                     f'apad=whole_dur={length:.9f},atrim=duration={length:.9f},asetpts=PTS-STARTPTS[a{index}]')
    graph.append('[a1][a2]concat=n=2:v=0:a=1[audio]')
    _ffmpeg(['-nostdin', '-f', 'concat', '-safe', '1', '-i', playlist, '-i', body, '-i', tail_audio,
             '-filter_complex_threads', '1', '-filter_complex', ';'.join(graph), '-map', '0:v:0',
             '-map', '[audio]', '-c:v', 'copy', '-c:a', 'aac', '-b:a', '160k',
             '-movflags', '+faststart', target])


def attach_outro(outro, timeline, run, fps, browser_channel):
    tail = append_outro_timeline(timeline, outro)
    clip, plates = render_outro(outro, run, fps, browser_channel)
    playlist = run / 'outro-concat.txt'
    for body, tail_audio, suffix in [(run/'news.mp4', clip, 'main'),
                                     (run/'news-no-bgm.mp4', outro['voice'], 'no-bgm')]:
        joined = run / f'news-outro-{suffix}.mp4'
        join_outro(body, clip, tail_audio, joined, tail['start'], outro['duration'], playlist)
        joined.replace(body)
    receipt = dict(tail, cards=outro['cards'], source_video_sha256=sha256(outro['video']),
                   voice_sha256=sha256(outro['voice']), inserted_clip_sha256=sha256(clip),
                   anthem=dict(title=outro['music']['title'], source_page=outro['music']['source_page'],
                               starts_at=round(tail['start']+outro['music']['placement_seconds'], 6)))
    with (run/'CREDITS.txt').open('a', encoding='utf8') as credits:
        credits.write('\n片尾制片人：' + ' · '.join(outro['cards'][0]['lines']) +
                      '\n参演人员：' + ' · '.join(outro['cards'][1]['lines']) +
                      '\n片尾音乐：南京农业大学之歌\n作词 王红谊 · 作曲 陶思耀\n' +
                      outro['music']['source_page']+'\n')
    return receipt, [clip, playlist, *plates]
