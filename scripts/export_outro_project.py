"""Rebuild the editable Shotcut outro from its checked-in media and card source."""
import argparse
import json
import wave
from pathlib import Path
from tempfile import TemporaryDirectory
from xml.etree import ElementTree as ET

from playwright.sync_api import sync_playwright


OUTRO = Path(__file__).resolve().parents[1] / 'assets/outro'
FPS = 60


def element(parent, tag, properties=None, **attributes):
    node = ET.SubElement(parent, tag, {name: str(value) for name, value in attributes.items()})
    for name, value in (properties or {}).items():
        ET.SubElement(node, 'property', name=name).text = str(value)
    return node


def render_cards(outro, cards, output, browser_channel):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel=browser_channel, headless=True)
        page = browser.new_page(viewport={'width': 1920, 'height': 1080})
        page.goto((outro / 'source/credits.html').as_uri())
        page.add_style_tag(content='html {width: 1920px; height: 1080px} '
                                   'body {position: absolute; left: 460px; top: 444px}')
        for index, card in enumerate(cards, 1):
            page.evaluate('card => window.showCredit(card)', card)
            page.evaluate('document.fonts.ready')
            longest = max(map(len, card['lines']))
            page.locator('.name').evaluate(
                '(node, size) => node.style.fontSize = size + "px"', max(30, min(67, 780 // longest)))
            if not page.locator('main').evaluate(
                    'm => m.scrollWidth <= m.clientWidth && m.scrollHeight <= m.clientHeight'):
                raise ValueError(f'片尾署名超出卡片尺寸：{card["label"]}')
            page.screenshot(path=str(output / f'credit-{index}.png'), omit_background=True)


def frames(seconds):
    return round(seconds * FPS)


def make_project(outro, current, music, cards, lines):
    total = frames(current['duration_seconds'])
    xml = ET.Element('mlt', {'LC_NUMERIC': 'C', 'title': 'Shotcut', 'producer': 'main_bin'})
    element(xml, 'profile', description='HD 1080p60', width=1920, height=1080,
            frame_rate_num=FPS, frame_rate_den=1, progressive=1, sample_aspect_num=1,
            sample_aspect_den=1, display_aspect_num=16, display_aspect_den=9, colorspace=709)
    element(xml, 'producer', {'resource': '0', 'mlt_service': 'color', 'length': total,
                              'mlt_image_format': 'rgba', 'set.test_audio': 0},
            id='black', out=total-1)
    background = element(xml, 'playlist', id='background')
    element(background, 'entry', producer='black', **{'in': 0, 'out': total-1})

    tracks = []
    clips = []

    def add_track(identifier, label, kind, path, start, length):
        clip_id = 'clip_' + identifier
        still = path.endswith('.png')
        if not still and not (outro / path).is_file():
            raise FileNotFoundError(outro / path)
        props = {'resource': path, 'mlt_service': 'qimage' if still else 'avformat',
                 'shotcut:caption': label}
        if still:
            props.update(length=15000, eof='pause')
        clip = element(xml, 'producer' if still else 'chain', props, id=clip_id, out=length-1)
        tracks.append((identifier, label, kind, clip_id, start, length))
        clips.append(clip_id)
        return clip

    add_track('music', '南京农业大学校歌', 'audio', music['bgm_clip'],
              frames(music['placement_seconds']), frames(music['duration_seconds']))
    for index, (speaker, line) in enumerate(zip(('秾小序', '楠小禾'), lines)):
        audio = f'editable/audio/voice-{index}.wav'
        with wave.open(str(outro / audio), 'rb') as recording:
            length = frames(recording.getnframes() / recording.getframerate())
        add_track(f'voice_{index}', speaker + '告别', 'audio', audio, frames(line['start']), length)
    add_track('picture', '片尾画面', 'video', music['default_video'], 0, total)
    for index, card in enumerate(cards, 1):
        length = frames(card['end']) - frames(card['start'])
        clip = add_track(f'credit_{index}', card['label'], 'video',
                         f'editable/credits/credit-{index}.png', frames(card['start']), length)
        fade_in = frames(0.45)
        element(clip, 'filter', {'mlt_service': 'brightness', 'shotcut:filter': 'fadeInBrightness',
                                  'level': 1, 'alpha': f'0=0;{fade_in}=1'}, out=fade_in)
        if index == len(cards):
            fade_out = frames(0.60)
            element(clip, 'filter', {'mlt_service': 'brightness', 'shotcut:filter': 'fadeOutBrightness',
                                      'level': 1, 'alpha': f'0=1;{fade_out-1}=0'},
                    **{'in': length-fade_out, 'out': length-1})

    for identifier, label, kind, clip_id, start, length in tracks:
        playlist = element(xml, 'playlist', {'shotcut:name': label, 'shotcut:'+kind: 1}, id=identifier)
        if start:
            element(playlist, 'blank', length=start)
        element(playlist, 'entry', producer=clip_id, **{'in': 0, 'out': length-1})

    main_bin = element(xml, 'playlist', {'xml_retain': 1}, id='main_bin')
    for clip in clips:
        element(main_bin, 'entry', producer=clip)
    tractor = element(xml, 'tractor', {'shotcut': 1}, id='tractor', out=total-1)
    element(tractor, 'track', producer='background')
    for identifier, _, kind, _, _, _ in tracks:
        element(tractor, 'track', producer=identifier, hide='video' if kind == 'audio' else 'audio')
    picture_index = next(index for index, track in enumerate(tracks, 1) if track[0] == 'picture')
    for index, (_, _, kind, _, _, _) in enumerate(tracks, 1):
        element(tractor, 'transition', {'mlt_service': 'mix', 'a_track': 0, 'b_track': index,
                                         'always_active': 1, 'sum': 1})
        if kind == 'video':
            bottom = index == picture_index
            element(tractor, 'transition', {'mlt_service': 'qtblend', 'a_track': 0 if bottom else picture_index,
                                             'b_track': index, 'disable': int(bottom), 'threads': 1})
    ET.indent(xml, space='  ')
    return ET.ElementTree(xml)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--outro', type=Path, default=OUTRO, help='Directory containing the outro files')
    parser.add_argument('--browser-channel', default='msedge')
    args = parser.parse_args()
    outro = args.outro.resolve()

    def read(name):
        return json.loads((outro / name).read_text(encoding='utf-8-sig'))

    current = read('CURRENT.json')
    music = read(current['music_config'])
    cards = read(current['credits_config'])['cards']
    lines = read('timeline.json')['lines']
    if len(lines) != 2 or len(cards) != 3:
        raise ValueError('片尾工程需要两句告别和三张署名卡')
    credits = outro / 'editable/credits'
    credits.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=credits) as staging:
        staging = Path(staging)
        render_cards(outro, cards, staging, args.browser_channel)
        project = staging / 'outro-edit.mlt'
        make_project(outro, current, music, cards, lines).write(project, encoding='utf-8', xml_declaration=True)
        for png in staging.glob('*.png'):
            png.replace(credits / png.name)
        project.replace(outro / project.name)


if __name__ == '__main__':
    main()
