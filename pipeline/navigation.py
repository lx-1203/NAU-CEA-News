"""Derive seekable programme navigation from measured final shot boundaries."""
import argparse
import html
import json
import math
from pathlib import Path
from .core import ROOT, read_json, write_json


def build_navigation(edition, timeline):
    stories = edition['stories']
    labels = {s['id']: s['name'] for s in read_json(ROOT/'config/pipeline.json')['editorial_policy']['sections']}
    chapters, seen = [], set()
    previous_end, previous_rank = 0.0, -1
    interludes={round(x['start'],6):x for x in timeline.get('interludes',[])}
    used_interludes=set()
    opening = timeline.get('opening')
    if opening:
        if opening.get('start') != 0 or not isinstance(opening.get('end'),(int,float)) or not math.isfinite(opening['end']) or opening['end'] <= 0:
            raise ValueError('开屏章节时间无效')
        previous_end = opening['end']
        chapters.append(dict(scene=-3,id='opening',title=opening.get('title','开屏'),
            section=None,section_title=None,start=0,end=previous_end))
    for shot in timeline['shots']:
        start, end = shot['start'], shot['end']
        scene = shot['scene']
        gap=interludes.get(round(previous_end,6))
        if gap:
            if abs(gap['end']-start)>.0001 or gap['end']<=gap['start']:raise ValueError('独立转场区间与正文不衔接')
            chapters.append(dict(scene=-4,id='transition-'+gap['section'],title='接下来｜'+gap['title'],
                section=None,section_title=None,start=gap['start'],end=gap['end']))
            used_interludes.add(round(previous_end,6));previous_end=gap['end']
        if (not isinstance(scene, int) or isinstance(scene, bool) or
            scene not in [-1, -2, *range(len(stories))] or
            not all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in (start, end)) or
            abs(start-previous_end) > .0001 or end <= start):
            raise ValueError('章节时间线不连续、无效或超出新闻范围')
        rank = len(stories) if scene == -2 else scene
        if rank < previous_rank: raise ValueError('新闻镜头次序错误')
        previous_end, previous_rank = end, rank
        group=('overview-'+shot['overview_section']) if shot.get('kind')=='overview' else scene
        if chapters and chapters[-1].get('_group') == group:
            chapters[-1]['end'] = end
            continue
        if group in seen: raise ValueError('新闻镜头不连续')
        seen.add(group)
        story = stories[scene] if scene >= 0 else None
        section = story.get('section', 'news') if story else None
        overview=shot.get('kind')=='overview'
        chapters.append(dict(_group=group,scene=scene, id=story['id'] if story else (group if overview else ('intro' if scene == -1 else 'outro')),
            title=story['title'] if story else ('目录｜'+labels[shot['overview_section']] if overview else ('开场' if scene == -1 else '结尾')),
            section=section, section_title=labels.get(section, '新闻' if section=='news' else section) if story else None,
            start=start, end=end))
    if not chapters or any(i not in seen for i in range(len(stories))):
        raise ValueError('时间线遗漏新闻，不能生成完整进度条')
    if used_interludes!=set(interludes):raise ValueError('存在未匹配的独立栏目转场')
    for chapter in chapters:chapter.pop('_group',None)
    sections = []
    for chapter in chapters:
        if chapter['section'] is None: continue
        if sections and sections[-1]['id'] == chapter['section']:
            sections[-1]['end'] = chapter['end']
        else:
            sections.append(dict(id=chapter['section'],title=chapter['section_title'],start=chapter['start'],end=chapter['end']))
    return dict(version=1, date=edition['date'], title=edition['title'], duration=previous_end,
                chapters=chapters, sections=sections, timing_basis='final_measured_shot_timeline')


def stamp(seconds):
    ms=round(seconds*1000)
    return f'{ms//3600000:02}:{ms//60000%60:02}:{ms//1000%60:02}.{ms%1000:03}'


def export_navigation(edition, timeline, output, video_src='news.mp4'):
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    nav=build_navigation(edition,timeline)
    write_json(output/'chapters.json',nav)
    vtt=['WEBVTT', '']
    metadata=[';FFMETADATA1']
    for i,c in enumerate(nav['chapters']):
        vtt += [str(i+1),f'{stamp(c["start"])} --> {stamp(c["end"])}',c['title'].replace('-->', '→').replace('\r',' ').replace('\n',' '),'']
        title=c['title'].replace('\\','\\\\').replace('\n',' ').replace('\r',' ')
        for char in '=;#':title=title.replace(char,'\\'+char)
        metadata += ['[CHAPTER]','TIMEBASE=1/1000',f'START={round(c["start"]*1000)}',f'END={round(c["end"]*1000)}',f'title={title}']
    (output/'chapters.vtt').write_text('\n'.join(vtt),encoding='utf8')
    (output/'chapters.ffmetadata').write_text('\n'.join(metadata)+'\n',encoding='utf8')
    assets=ROOT/'assets/player'
    css=(assets/'news-player.css').read_text('utf8')
    js=(assets/'news-player.js').read_text('utf8')
    payload=json.dumps(nav,ensure_ascii=False).replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')
    document=f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(edition['title'])} · {html.escape(edition['date'])}</title><style>{css}</style></head><body>
<main><header><small>NJAU-CEA · {html.escape(edition['date'])}</small><h1>{html.escape(edition['title'])}</h1></header>
<section class="news-player"><video controls preload="metadata" playsinline src="{html.escape(str(video_src),quote=True)}"></video>
<div class="player-navigation"><div class="seek-wrap"><div class="section-track" aria-hidden="true"></div><div class="played-track"></div><div class="chapter-marks" aria-hidden="true"></div><input class="seek" type="range" min="0" max="{nav['duration']}" step="0.1" value="0" aria-label="拖动调整视频进度"></div>
<div class="transport"><button class="play" type="button">播放</button><output class="clock">00:00 / 00:00</output><span class="current-chapter"></span><button class="mute" type="button" aria-label="静音" aria-pressed="false">静音</button><button class="fullscreen" type="button">全屏</button></div><div class="section-buttons" aria-label="按栏目跳转"></div></div></section>
<nav class="chapter-list" aria-label="按新闻跳转"></nav><p class="player-note">拖动进度条，或点击栏目、新闻跳转。视频文件中的章节显示取决于播放器支持。</p></main>
<script id="news-navigation" type="application/json">{payload}</script><script>{js}</script></body></html>'''
    (output/'watch.html').write_text(document,encoding='utf8')
    return nav


def main():
    parser=argparse.ArgumentParser(description='只生成新闻章节和可跳转播放器，不渲染或改动视频')
    parser.add_argument('--edition',type=Path,required=True)
    parser.add_argument('--timeline',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--video',default='news.mp4')
    args=parser.parse_args()
    export_navigation(read_json(args.edition),read_json(args.timeline),args.output,args.video)
    print(f'PLAYER: {args.output.resolve()/"watch.html"}')


if __name__=='__main__':main()
