"""Project adapter for the installed IndexTTS2 client (one serial batch)."""
import math
import os
import shutil
import subprocess
import sys
import wave
from pathlib import Path
from urllib.parse import urlsplit

import requests
from .core import read_json, write_json, sha256


def edition_lines(edition):
    title=edition.get('title','NJAU-CEA 新闻联播')
    spoken_title=title.replace('NJAU-CEA','N J A U C E A').replace('njau-cea','N J A U C E A').replace('NAUCEA','N A U C E A')
    lines = [dict(text='这里是南京农业大学计算机爱好者协会。', scene=-1, anchor='xiaoXu'),
             dict(text='欢迎收看'+title.replace(' ','')+'。', spoken_text='欢迎收看 '+spoken_title+'。', scene=-1, anchor='xiaoXu'),
             dict(text=f'今天是{int(edition["date"][5:7])}月{int(edition["date"][8:])}日，回顾昨天的资讯。', scene=-1, anchor='xiaoHe')]
    if edition.get('section_overviews') is not None:
        from .programme import section_cards
        cards=section_cards(edition)
        overviews=edition['section_overviews']
        if not isinstance(overviews,dict) or set(overviews)!={c['id'] for c in cards}:
            raise ValueError('总览口播必须覆盖实际全部栏目')
        for i,card in enumerate(cards):
            text=overviews[card['id']]
            if not isinstance(text,str) or not text.strip() or len(text)>22:raise ValueError('栏目总览口播需为22字内文本')
            lines.append(dict(text=text,scene=-1,anchor='xiaoXu' if i%2==0 else 'xiaoHe',kind='overview',overview_section=card['id']))
    briefs=edition.get('opening_briefs',[])
    if not isinstance(briefs,list) or len(briefs)>3 or any(not isinstance(t,str) or not t.strip() or len(t)>22 for t in briefs):
        raise ValueError('开场三条导语需为最多3句文本，每句至多22字')
    if not edition.get('section_overviews'):
        lines.extend(dict(text=text,scene=-1,anchor='xiaoXu' if i%2==0 else 'xiaoHe') for i,text in enumerate(briefs))
    for i, story in enumerate(edition['stories']):
        lines.extend(dict(text=text, scene=i, anchor='xiaoXu' if i % 2 == 0 else 'xiaoHe') for text in story['narration'])
    lines.extend([dict(text='完整来源和图文日报已随本期保存。', scene=-2, anchor='xiaoXu'),
                  dict(text='让技术更有温度，我们下期再见。', scene=-2, anchor='xiaoHe')])
    for index,annotation in edition.get('speech_annotations',{}).items():
        if not str(index).isdigit() or not 0<=int(index)<len(lines):raise ValueError('读音注释句序号无效')
        if not isinstance(annotation,dict):raise ValueError('读音注释必须是对象')
        if 'spoken_text' in annotation and (not isinstance(annotation['spoken_text'],str) or not annotation['spoken_text'].strip()):raise ValueError('spoken_text必须是非空读音文本')
        if 'sensitive' in annotation and not isinstance(annotation['sensitive'],bool):raise ValueError('sensitive必须为布尔值')
        for field in ['spoken_text','sensitive']:
            if field in annotation:lines[int(index)][field]=annotation[field]
    return lines


def validate_audio_entries(lines, entries, base):
    if set(entries) != {str(i) for i in range(len(lines))}:
        raise ValueError('外部配音必须完整覆盖全部句子，禁止混用备用语音')
    for i, line in enumerate(lines):
        item = entries[str(i)]
        if item['text'] != line['text']: raise ValueError('外部配音文本与当前稿件不一致')
        path = (base / item['path']).resolve()
        if not path.is_file(): raise ValueError(f'外部配音缺失: {path}')
        if item.get('sha256') and sha256(path) != item['sha256']:
            raise ValueError(f'外部配音哈希不一致: {path}')
    return entries


def validate_batch(lines, result, voices):
    records = result.get('items', [])
    wanted = {f'cue-{i:03d}' for i in range(len(lines))}
    if result.get('ok') is not True or len(records) != len(lines) or {x['id'] for x in records} != wanted:
        raise ValueError('工作台合成未完整成功，保留原成片')
    by_id = {x['id']: x for x in records}
    entries = {}
    for i, line in enumerate(lines):
        rec = by_id[f'cue-{i:03d}']
        if rec.get('ok') is not True or rec.get('mel_capped'):
            raise ValueError(f'工作台第 {i+1} 句失败或截断')
        path = Path(rec['out']).resolve()
        with wave.open(str(path)) as audio:
            duration = audio.getnframes() / audio.getframerate()
        if not math.isfinite(duration) or duration <= 0 or abs(duration-float(rec['duration'])) > .05:
            raise ValueError('工作台音频时长与记录不一致')
        entries[str(i)] = dict(text=line['text'], spoken_text=line.get('spoken_text',line['text']), path=str(path), voice='IndexTTS2 / '+voices[line['anchor']]['name'],
                               sha256=sha256(path), duration=duration)
    return entries


def workbench_dependencies(config):
    if config.get('speech', {}).get('provider') != 'indextts2': return []
    wb = config['speech']['workbench']
    engine=Path(wb['project_dir'])
    return [Path(wb['client']), *[Path(v['reference']) for v in wb['voices'].values()],
            *[p for p in [engine/'server.py',engine/'indextts/infer_v2.py',engine/'indextts/utils/checkpoint.py'] if p.is_file()]]


def client_environment(wb):
    env = dict(os.environ, PYTHONIOENCODING='utf-8', INDEXTTS_HEADLESS='1',
               INDEXTTS_PROJECT_DIR=wb['project_dir'], INDEXTTS_CONFIG_DIR=wb['client_config_dir'],
               INDEXTTS_OUT_DIR=wb['output_root'])
    state = read_json(wb['state_file'])
    url = state['url'].rstrip('/')
    parts = urlsplit(url)
    if parts.scheme != 'http' or parts.hostname not in {'localhost', '127.0.0.1'} or parts.username or parts.password:
        raise ValueError('工作台仅允许本机 HTTP 地址')
    env['INDEXTTS_URL'] = url
    if wb.get('low_memory_load'):env['INDEXTTS_LOW_MEMORY_LOAD']='1'
    return env


def start_workbench(config,wb,run_dir):
    env=dict(os.environ)
    if wb.get('low_memory_load'):env['INDEXTTS_LOW_MEMORY_LOAD']='1'
    # A Windows background descendant can inherit a capture pipe and prevent
    # communicate() receiving EOF after the launcher has already exited.
    with (run_dir/'workbench-start.log').open('wb') as log:
        startup=subprocess.run([config['speech_shell'],'-NoProfile','-File',wb['start_script'],'-NoBrowser'],
                               stdout=log,stderr=subprocess.STDOUT,env=env,timeout=180)
    if startup.returncode:raise RuntimeError('工作台启动失败，详见 workbench-start.log')


def run_workbench_batch(args,env,run_dir,session):
    for attempt in range(2):
        command=[*args,*(['--resume'] if attempt else [])]
        with (run_dir/'workbench-result.json').open('wb') as stdout,(run_dir/'workbench-progress.log').open('wb') as stderr:
            result=subprocess.run(command,env=env,stdout=stdout,stderr=stderr,timeout=3600)
        if result.returncode==0:return
        progress=(run_dir/'workbench-progress.log').read_text(encoding='utf8',errors='replace')
        if attempt or 'CUDA out of memory' not in progress:break
        # A completed failed inference may leave allocator workspaces cached.
        # The workbench's idle status refresh releases that cache. Retry only
        # once, with its content fingerprints protecting completed recordings.
        response=session.get(env['INDEXTTS_URL']+'/api/v1/status',timeout=30);response.raise_for_status()
        status=response.json();write_json(run_dir/'workbench-warm-retry.json',status)
        if status.get('generating') or status.get('loaded') is not True:break
        for name in ['workbench-result.json','workbench-progress.log']:
            p=run_dir/name;shutil.copy2(p,p.with_name(p.stem+'-attempt1'+p.suffix))
    raise RuntimeError('工作台合成失败，详见 workbench-progress.log；原成片保留')


def prepare_workbench_audio(lines, config, run_dir, day):
    wb = config['speech']['workbench']
    from .storage import issue_paths
    paths=issue_paths(day)
    cache = paths['audio_source']/run_dir.name if Path(run_dir).resolve().is_relative_to(paths['runs']) else Path(wb['output_root'])/day/run_dir.name
    cache.mkdir(parents=True, exist_ok=True)
    session = requests.Session(); session.trust_env = False
    try:
        env = client_environment(wb)
        response = session.get(env['INDEXTTS_URL']+'/api/v1/health', timeout=10)
        response.raise_for_status()
        health = response.json()
        if health.get('ok') is not True and health.get('status') != 'ok': raise RuntimeError('工作台健康检查失败')
    except (OSError, requests.RequestException, ValueError, RuntimeError):
        # Use the installed launcher, which handles port discovery and reuses its own instance.
        start_workbench(config,wb,run_dir)
        env = client_environment(wb)
    status_response = session.get(env['INDEXTTS_URL']+'/api/v1/status', timeout=15)
    status_response.raise_for_status()
    status = status_response.json()
    write_json(run_dir/'workbench-status.json', status)
    if status.get('generating'): raise RuntimeError('工作台已有其他合成任务，本期不并发抢占 GPU')
    tasks = []
    for i, line in enumerate(lines):
        voice = wb['voices'][line['anchor']]
        if sha256(voice['reference']) != voice['sha256']: raise ValueError('主播参考音频哈希变化')
        tasks.append(dict(id=f'cue-{i:03d}', text=line.get('spoken_text',line['text']), voice=voice['reference'],
                          out=str(cache/f'cue-{i:03d}.wav'), rate=voice.get('rate', 1.0)))
    spec = dict(defaults=wb['parameters'], items=tasks)
    write_json(run_dir/'workbench-tasks.json', spec)
    client = wb['client']
    # Read pronunciation preview before GPU synthesis; never modify the global glossary silently.
    text_path = run_dir/'workbench-script.txt'
    text_path.write_text('\n'.join(line.get('spoken_text',line['text']) for line in lines), encoding='utf-8')
    preview = subprocess.run([sys.executable, client, 'segments', '--text-file', str(text_path),
                              '--seg-tokens', str(wb['parameters'].get('seg_tokens', 120))],
                             env=env, capture_output=True, timeout=60)
    (run_dir/'workbench-preview.json').write_bytes(preview.stdout)
    if preview.returncode: raise RuntimeError('工作台读音预览失败')
    print(f'IndexTTS2: 开始串行生成 {len(lines)} 句，日志 {run_dir / "workbench-progress.log"}', flush=True)
    run_workbench_batch([sys.executable,client,'batch','-f',str(run_dir/'workbench-tasks.json'),
                        '--outdir',str(cache),'--manifest-out',str(run_dir/'workbench-batch.json'),
                        '--lock-wait','0','--no-start','--fail-fast'],env,run_dir,session)
    entries = validate_batch(lines, read_json(run_dir/'workbench-result.json'), wb['voices'])
    write_json(run_dir/'audio-manifest.json', entries)
    write_json(run_dir/'workbench-provenance.json', dict(provider='indextts2', url=env['INDEXTTS_URL'],
               client_sha256=sha256(client), voices=wb['voices'], parameters=wb['parameters']))
    return entries
