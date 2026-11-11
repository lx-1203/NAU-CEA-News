"""Reusable sentence performance and source-media planning; no GPU required."""
import math
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit
from .core import ROOT, read_json, sha256, validate_edition
from .workbench import edition_lines
from .date_guard import validate_date_proof
from .layout import validate_framing, key_facts
from .performance import COMMON_STATES, ASSET_VARIANTS, plan_performances, performance_audit


def expression_assets():
    """Use the studio's existing whole-character art as the single asset map."""
    text = (ROOT/'script.js').read_text(encoding='utf8')
    result = {}
    for anchor in ['xiaoXu', 'xiaoHe']:
        body = re.search(r'\b'+anchor+r':\s*\{([^}]+)\}', text).group(1)
        result[anchor] = {key: ROOT/'assets/characters'/value for key,value in
                          re.findall(r"(\w+):\s*'([^']+)'", body)}
    return result


def anchor_library_manifest_path():
    local = ROOT/'config/anchor-library.local.json'
    return local if local.is_file() else ROOT/'config/anchor-library.json'


def validate_anchor_library(assets=None):
    """Validate both complete shared libraries before spending time on speech."""
    assets = expression_assets() if assets is None else assets
    manifest = read_json(anchor_library_manifest_path())
    for anchor in ['xiaoXu', 'xiaoHe']:
        records = manifest.get('anchors', {}).get(anchor, {})
        for state in COMMON_STATES:
            record = records.get(state, {})
            variants = record.get('variants', [dict(record, expression=state)])
            expected = ASSET_VARIANTS[state]
            if (len(variants) != len(expected) or
                    len({v.get('sha256') for v in variants}) != len(expected) or
                    variants[0].get('path') != record.get('path') or
                    variants[0].get('sha256') != record.get('sha256')):
                raise ValueError(f'共同主播库变体数量或首图不符: {anchor}/{state}')
            for expression, variant in zip(expected, variants):
                path = assets.get(anchor, {}).get(expression)
                if (variant.get('expression') != expression or path is None or not path.is_file() or
                        path.resolve() != (ROOT/variant.get('path', '')).resolve() or
                        sha256(path) != variant.get('sha256')):
                    raise ValueError(f'共同主播库缺失或哈希不符: {anchor}/{expression}')
    return manifest


def performance_events(line, duration, intervals, override=None):
    """Semantic pose cue, then bind to measured speech (approximate, not word alignment)."""
    override = override or {}
    if not math.isfinite(duration) or duration <= 0 or not intervals:
        raise ValueError('表演时间线需要实际发声时长')
    anchor = line['anchor']
    choice = plan_performances([line], [], {'0': override})[0]
    base, focus, action, ratio = (choice[k] for k in ['base', 'expression', 'action', 'focus_ratio'])
    assets = expression_assets()[anchor]
    if focus not in assets or base not in assets:
        raise ValueError(f'无效表情: {anchor}/{focus}')
    first, last = intervals[0][0], intervals[-1][1]
    if not 0 <= first < last <= duration+.001: raise ValueError('发声区间超出句子时长')
    remaining = sum(b-a for a,b in intervals)*ratio
    middle = first
    for a,b in intervals:
        if remaining < b-a:
            middle = a+remaining
            break
        remaining -= b-a
    settle = min(duration, last+.02)
    return [dict(at=0.0, expression=base, action='hold'),
            dict(at=round(middle,6), expression=focus, action=action),
            dict(at=round(settle,6), expression=base, action='hold')]


def media_for_shot(selected, cache):
    """Share a local copy, while retaining each shot's trim and editorial metadata."""
    if not selected: return None
    return dict(cache[selected['path']], **{k:v for k,v in selected.items() if k != 'path'})


def resolve_media(item, edition_dir):
    kind, role = item.get('kind'), item.get('role')
    origin = urlsplit(item.get('source_url',''))
    if (str(item.get('asset_url','')).startswith('editorial://') or
            item.get('is_programmatic_editorial_art') is True or
            item.get('production_method') in {'svg','canvas','pillow','programmatic'} or
            any(t in item.get('caption','') for t in ['编辑流程示意图','编辑示意图','编辑事实图'])):
        raise ValueError('禁止以自行绘制的程序图替代图片素材；请补充原始素材或图像工具输出')
    if kind not in {'image','video'} or role not in {'current','archive','source_capture'}:
        raise ValueError('素材类型或画面用途无效')
    if role=='source_capture':raise ValueError('文字核验截图仅留存证，不得作为入画素材')
    if origin.scheme not in {'http','https'} or not origin.netloc or not item.get('caption'):
        raise ValueError('素材缺少可回溯原始来源或画面说明')
    if item.get('published_at') is None:
        if not (role=='archive' and item.get('media_date_precision')=='unknown' and
                item.get('original_asset_first_publication_unknown') is True and
                str(item.get('media_date_note','')).strip()):
            raise ValueError('素材首发未知只可作明确说明的资料画面，不能伪造日期')
    else:
        try:published = datetime.fromisoformat(item['published_at'])
        except (TypeError,ValueError):raise ValueError('素材发布日期无效')
        if published.tzinfo is None: raise ValueError('素材发布日期需要时区')
    if role == 'archive' and '资料' not in item['caption']: raise ValueError('历史资料画面必须在画面上标注资料')
    path = (Path(edition_dir)/item['path']).resolve()
    if not path.is_file() or sha256(path) != item.get('sha256'): raise ValueError(f'素材不存在或哈希不符: {path}')
    offset = item.get('offset',0)
    if not isinstance(offset,(int,float)) or not math.isfinite(offset) or offset < 0: raise ValueError('素材起点无效')
    framing = validate_framing(item.get('framing'))
    if kind == 'video' and framing['crop'] != [0,0,1,1]:
        raise ValueError('原视频必须保留完整比例及水印')
    return dict(item, path=str(path), offset=offset, framing=framing)


def production_plan(edition_path, require_media=None):
    edition_path = Path(edition_path).resolve()
    edition = validate_edition(read_json(edition_path))
    assets = expression_assets()
    library = validate_anchor_library(assets)
    if not edition.get('archive_production'):
        validate_date_proof(edition,edition_path.parent)
    config = read_json(ROOT/'config/pipeline.json')
    if require_media is None: require_media = config.get('media_policy',{}).get('require_source_media',False)
    media = {}
    for i, story in enumerate(edition['stories']):
        key_facts(story)
        media[i] = [resolve_media(item, edition_path.parent) for item in story.get('media',[])]
        if require_media and not media[i]: raise ValueError(f'{story["id"]} 缺少已回源的新闻素材')
    positions, shots = {}, []
    lines = edition_lines(edition)
    overrides = edition.get('performance')
    if config.get('outro', {}).get('enabled'):
        dropped = {str(i) for i, line in enumerate(lines) if line['scene'] == -2}
        lines = [line for line in lines if line['scene'] != -2]
        if isinstance(overrides, dict):
            overrides = {key: value for key, value in overrides.items() if key not in dropped}
    performances = plan_performances(lines, edition['stories'], overrides)
    for index, line in enumerate(lines):
        scene = line['scene']
        position = positions.get(scene,0)
        choices = media.get(scene,[])
        chosen = choices[position % len(choices)] if choices else None
        # Validate defaults/overrides before any speech generation; actual times bind later.
        override = performances[index]
        preview = performance_events(line,1.0,[(.1,.9)],override)
        for event in preview:
            expression = event['expression']
            if not assets[line['anchor']][expression].is_file():
                raise ValueError(f'缺少完整人物素材: {line["anchor"]}/{expression}')
        shots.append(dict(cue=index, **line, media=chosen, performance=override,
                          preview_events=preview, timing='按实际发声区间绑定；句内触发为比例近似'))
        positions[scene] = position+1
    return dict(date=edition['date'], edition=str(edition_path), shots=shots, anchor_library_version=library['version'], performance_audit=performance_audit(shots),
                speech_provider=config.get('speech',{}).get('provider'),
                voices=config.get('speech',{}).get('workbench',{}).get('voices',{}))
