import hashlib
import json
import math
import re
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
TZ = ZoneInfo('Asia/Shanghai')


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(path)


def sha256(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def coverage(day):
    end = datetime.strptime(day, '%Y-%m-%d').replace(tzinfo=TZ)
    return end - timedelta(days=1), end


def canonical_url(url):
    p = urlsplit(url)
    query = [(k, v) for k, v in parse_qsl(p.query) if k not in {'f', 'from', 'ref', 'source'} and not k.startswith('utm_')]
    return urlunsplit((p.scheme, p.netloc.lower(), p.path.rstrip('/'), urlencode(query), ''))


def normalize_items(items):
    seen, result = set(), []
    for item in items:
        key = canonical_url(item.get('source_url', ''))
        if not key or key in seen: continue
        seen.add(key)
        result.append(dict(item, source_url=key))
    return result


def validate_edition(edition):
    start, end = coverage(edition['date'])
    stories = edition.get('stories', [])
    limit = read_json(ROOT/'config/pipeline.json')['max_stories']
    if not 1 <= len(stories) <= limit: raise ValueError(f'每期需要 1–{limit} 条已核实新闻')
    if len(normalize_items(stories)) != len(stories): raise ValueError('重复新闻来源链接')
    legacy_sections = (None, '头条', '必读', '该知道', '顺手存')
    if edition.get('section_schema_version') == 1 or len(stories) > 8 or any(s.get('section') not in legacy_sections for s in stories):
        validate_sections(edition)
    ids = set()
    for s in stories:
        if not re.fullmatch(r'[A-Za-z0-9_-]+', s['id']) or s['id'] in ids: raise ValueError('新闻 ID 无效或重复')
        ids.add(s['id'])
        if s.get('verified') is not True or not s.get('verification_note', '').strip(): raise ValueError('新闻未完成回源核实')
        published = datetime.fromisoformat(s['published_at'])
        if published.tzinfo is None or not start <= published < end: raise ValueError('新闻时间缺时区或不在本期覆盖范围')
        original = s.get('original_publication_date')
        if original != start.date().isoformat(): raise ValueError('原始发布日期不在本期，不能把转载当新消息')
        p = urlsplit(s['source_url'])
        if p.scheme not in {'http', 'https'} or not p.netloc: raise ValueError('来源链接无效')
        for field in ['title', 'summary', 'source_name']:
            if not isinstance(s.get(field), str) or not s[field].strip(): raise ValueError(f'缺少 {field}')
        if len(s['title']) > 26: raise ValueError('标题超过 26 字')
        if not isinstance(s.get('visual_labels'), list) or not 1 <= len(s['visual_labels']) <= 4 or any(not isinstance(x, str) or not x.strip() or len(x) > 12 for x in s['visual_labels']): raise ValueError('每条新闻需 1–4 个与原文对应的图示标签，每个至多 12 字')
        if not isinstance(s.get('narration'), list) or not s['narration'] or any(not isinstance(x, str) or not x.strip() or len(x) > 22 for x in s['narration']): raise ValueError('口播逐句填写，每句至多 22 字')
    return edition


def validate_sections(edition):
    sections = read_json(ROOT/'config/pipeline.json')['editorial_policy']['sections']
    order = {s['id']: i for i, s in enumerate(sections)}
    counts = {s['id']: 0 for s in sections}
    events, titles, previous = set(), set(), -1
    for story in edition['stories']:
        section = story.get('section')
        if section not in order or order[section] < previous: raise ValueError('栏目缺失、未知或顺序错误')
        previous = order[section]
        counts[section] += 1
        event = story.get('event_id')
        if not isinstance(event, str) or not event.strip(): raise ValueError('新闻缺少跨栏目去重 event_id')
        title = re.sub(r'\s+', '', story['title'])
        if event in events or title in titles: raise ValueError('事件重复：头条与其他栏目不能重复')
        events.add(event); titles.add(title)
    notes = edition.get('section_notes', {})
    if not isinstance(notes, dict): raise ValueError('栏目缺额说明需要对象')
    for section in sections:
        count, target = counts[section['id']], section['count']
        if count > target: raise ValueError(f'{section["name"]}超过{target}条')
        if count < target and not str(notes.get(section['id'], '')).strip():
            raise ValueError(f'{section["name"]}缺额，需记录扩源与核实结果')


def make_cues(texts, durations):
    if len(texts) != len(durations): raise ValueError('字幕和音频数量不一致')
    cues, pos = [], 0.0
    for text, duration in zip(texts, durations):
        if not math.isfinite(duration) or duration <= 0: raise ValueError('音频时长无效')
        cues.append(dict(text=text, start=round(pos, 6), end=round(pos + duration, 6)))
        pos += duration
    return cues
