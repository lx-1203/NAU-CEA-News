"""Reject stale daily issues and publication dates supported only by discovery feeds."""
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit
from .core import ROOT, TZ, coverage, canonical_url, sha256


def validate_issue_day(day, today=None, archive=False):
    today = today or datetime.now(TZ).date()
    issue = datetime.strptime(day, '%Y-%m-%d').date()
    if archive and issue == today:
        raise ValueError('今日版不能使用历史补制例外跳过首发核验')
    if issue > today or (issue != today and not archive):
        raise ValueError('今日版刊期必须是北京时间今天；历史补制需显式 --archive，不能冒称今日资讯')


def validate_date_proof(edition, base_dir=ROOT):
    start, end = coverage(edition['date'])
    for story in edition['stories']:
        proof = story.get('date_evidence') or {}
        if proof.get('kind') != 'original_publication':
            raise ValueError(f'{story["id"]}: 缺原始首发证据，转载/更新/帖子时间不能代替')
        url = proof.get('source_url', '')
        if urlsplit(url).scheme not in {'http','https'} or canonical_url(url) != canonical_url(story['source_url']):
            raise ValueError('日期证据必须对应当前新闻的原始来源')
        try:
            published = datetime.fromisoformat(proof['published_at'])
            claimed = datetime.fromisoformat(story['published_at'])
        except (KeyError,ValueError,TypeError):
            raise ValueError('首发证据缺少可解析的带时区时间')
        if published.tzinfo is None or claimed.tzinfo is None or published != claimed or not start <= published < end:
            raise ValueError('首发证据时间与稿件不符或不在昨天完整自然日')
        if story.get('time_precision') == 'day' and proof.get('source_timezone') != 'Asia/Shanghai':
            raise ValueError('海外来源只有日期、时区边界不明，不能认定属于北京时间昨天')
        if proof.get('event_date') != start.date().isoformat() or not proof.get('event_date_note','').strip():
            raise ValueError('事件/新增进展不在昨天，不能用新报道包装旧事件')
        path = Path(base_dir)/proof.get('path','')
        if not path.is_file() or sha256(path) != proof.get('sha256'):
            raise ValueError('首发日期原文存证不存在或哈希变化')
        quote = proof.get('date_text','').strip()
        if not quote or quote not in path.read_text(encoding='utf-8-sig'):
            raise ValueError('日期引文在实际归档原文中不存在')
    return edition
