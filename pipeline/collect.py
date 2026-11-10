"""Collect candidates only. Never label feed text as verified editorial copy."""
import concurrent.futures
import html
import re
import xml.etree.ElementTree as ET
from datetime import datetime
from email.utils import parsedate_to_datetime
import requests
from .core import ROOT, TZ, read_json, write_json, coverage, normalize_items


def clean(text):
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', html.unescape(text or ''))).strip()


def parse_date(text):
    text = re.sub(r'\s+', ' ', text.strip())
    try: value = datetime.fromisoformat(text.replace('Z', '+00:00').replace(' +', '+').replace(' -', '-'))
    except ValueError: value = parsedate_to_datetime(text)
    if value.tzinfo is None: raise ValueError('来源日期缺时区')
    return value.astimezone(TZ).isoformat()


def candidate_date_metadata(kind, timestamp):
    return dict(date_basis={'hn':'submission_time','hf':'paper_metadata_time','rss':'feed_claimed_time'}.get(kind,'unknown'),
                discovery_timestamp=timestamp, original_published_at=None,
                original_date_status='unverified',
                date_warning='仅为候选筛选时间；须回读原始首发时间和事件日期，不能直接进入今日稿件')


def fetch(source):
    r = requests.get(source['url'], headers={'User-Agent': 'Mozilla/5.0 NAU-CEA-News/1.0', 'Referer': source['url']}, timeout=20)
    r.raise_for_status()
    result = []
    if source['kind'] == 'rss':
        root = ET.fromstring(r.content)
        entries = root.findall('.//item')
        if not entries:
            for e in root.findall('{http://www.w3.org/2005/Atom}entry'):
                ns = '{http://www.w3.org/2005/Atom}'
                result.append(dict(title=clean(e.findtext(ns+'title')), source_url=e.findtext(ns+'id'), published_at=parse_date(e.findtext(ns+'published')), excerpt=clean(e.findtext(ns+'summary'))[:3000]))
        for e in entries:
            try: published = parse_date(e.findtext('pubDate') or '')
            except (ValueError, TypeError): continue
            result.append(dict(title=clean(e.findtext('title')), source_url=e.findtext('link'), published_at=published, excerpt=clean(e.findtext('description'))[:3000]))
    elif source['kind'] == 'hn':
        for e in r.json()['hits']:
            if e.get('url'): result.append(dict(title=e['title'], source_url=e['url'], published_at=parse_date(e['created_at']), excerpt=clean(e.get('story_text'))[:3000]))
    elif source['kind'] == 'hf':
        for e in r.json():
            p = e['paper']
            result.append(dict(title=p['title'], source_url='https://huggingface.co/papers/'+p['id'], published_at=parse_date(p['publishedAt']), excerpt=clean(p.get('summary'))[:3000]))
    return [dict(e, source_name=source['name'], verified=False,
                 **candidate_date_metadata(source['kind'],e['published_at'])) for e in result]


def collect(day, output):
    start, end = coverage(day)
    config = read_json(ROOT/'config/pipeline.json')
    items, statuses = [], []
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        futures = {pool.submit(fetch, s): s for s in config['sources']}
        for future in concurrent.futures.as_completed(futures):
            source = futures[future]
            try:
                found = future.result()
                eligible = [s for s in found if start <= datetime.fromisoformat(s['published_at']) < end]
                items.extend(eligible)
                statuses.append(dict(name=source['name'], url=source['url'], status='ok', fetched=len(found), in_window=len(eligible)))
            except Exception as exc:
                statuses.append(dict(name=source['name'], url=source['url'], status='failed', error=str(exc)))
    result = dict(date=day, collected_at=datetime.now(TZ).isoformat(), coverage_start=start.isoformat(), coverage_end=end.isoformat(), editorial_ready=False,
                  date_policy='discovery_only; original publication and event dates require archived proof before production',
                  sources=statuses, items=sorted(normalize_items(items), key=lambda x: x['published_at'], reverse=True))
    write_json(output, result)
    if not result['items']: raise RuntimeError(f'本期没有候选新闻；详见 {output}')
    return result
