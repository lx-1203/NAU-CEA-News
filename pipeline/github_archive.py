"""Publish reviewed, public-only daily Markdown. Never uploads media or local evidence."""
import base64
import hashlib
import os
import re
import shutil
import subprocess
from pathlib import Path
from urllib.parse import quote, urlsplit, parse_qsl
import requests
from .core import ROOT, coverage, read_json, write_json, sha256, validate_edition
from .date_guard import validate_date_proof


def credential_token():
    if os.environ.get('GITHUB_TOKEN'):return os.environ['GITHUB_TOKEN']
    candidates=[ROOT/'.tools/gh/bin/gh.exe',ROOT/'runtime/gh/bin/gh.exe']
    executable=next((str(p) for p in candidates if p.is_file()),None) or shutil.which('gh')
    if executable:
        try:result=subprocess.run([executable,'auth','token','--hostname','github.com'],capture_output=True,text=True,timeout=20)
        except (OSError,subprocess.TimeoutExpired):return ''
        if result.returncode==0:return result.stdout.strip()
    return ''


def public_markdown(edition):
    sections={s['id']:s['name'] for s in read_json(ROOT/'config/pipeline.json')['editorial_policy']['sections']}
    day=coverage(edition['date'])[0].date().isoformat()
    lines=[f'# {edition["date"]} · {edition["title"]}', '',
        f'覆盖日期：{day}（北京时间完整自然日） · 共{len(edition["stories"])}条', '',
        '本文为新闻稿与口播稿，图片、视频及音色文件不随稿件上传。', '']
    if edition.get('publication_note'):lines += ['版本说明：'+edition['publication_note'],'']
    previous=None
    for i,s in enumerate(edition['stories'],1):
        parts=urlsplit(s['source_url'])
        if parts.username or parts.password or any(k.lower() in {'token','api_key','access_token','key','secret'} for k,_ in parse_qsl(parts.query)):
            raise ValueError('来源URL含非公开凭据，不能上传')
        section=s.get('section','news')
        if section!=previous:
            lines += [f'## {sections.get(section,"新闻" if section=="news" else section)}', ''];previous=section
        lines += [f'### {i}. {s["title"]}', '', s['summary'], '']
        if s.get('why_it_matters'):lines += ['读者关联：'+s['why_it_matters'], '']
        lines += ['口播：', '', *['> '+text for text in s['narration']], '',
            f'来源：[{s["source_name"]}]({s["source_url"]})',
            f'原始发布日期：{s["original_publication_date"]}；发布时间：{s["published_at"]}', '']
    return '\n'.join(lines).rstrip()+'\n'


def push_markdown(repository, day, text, token, *, session=None, branch=None):
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',repository or ''):
        raise ValueError('GitHub仓库应为owner/repo，不接受令牌或任意API地址')
    coverage(day)
    if not token:raise ValueError('缺GitHub认证；请配置GITHUB_TOKEN')
    session=session or requests.Session()
    headers={'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json',
             'X-GitHub-Api-Version':'2026-03-10','User-Agent':'NAU-CEA-News-Archive'}
    base='https://api.github.com/repos/'+repository
    repo=session.get(base,headers=headers,timeout=30)
    if repo.status_code!=200:raise RuntimeError(f'仓库读取失败（HTTP {repo.status_code}）；令牌未写入日志')
    info=repo.json()
    if info.get('private') is not False:raise ValueError('目标不是公开仓库，尚未执行写入')
    branch=branch or info.get('default_branch','main')
    path=f'news/{day[:4]}/{day[5:7]}/{day}.md'
    url=base+'/contents/'+quote(path,safe='/')
    current=session.get(url,params={'ref':branch},headers=headers,timeout=30)
    if current.status_code not in (200,404):raise RuntimeError(f'归档读取失败（HTTP {current.status_code}）')
    blob=text.encode('utf8')
    if len(blob)>900000:raise ValueError('新闻稿超过归档体积上限')
    git_sha=hashlib.sha1(b'blob '+str(len(blob)).encode()+b'\0'+blob).hexdigest()
    if current.status_code==200 and current.json().get('sha')==git_sha:
        return dict(status='unchanged',repository=repository,path=path,
                    url=f'https://github.com/{repository}/blob/{quote(branch,safe="")}/{path}')
    payload=dict(message=f'news: {day} daily briefing',content=base64.b64encode(blob).decode('ascii'),branch=branch)
    if current.status_code==200:payload['sha']=current.json()['sha']
    result=session.put(url,headers=headers,json=payload,timeout=45)
    if result.status_code not in (200,201):raise RuntimeError(f'GitHub写入失败（HTTP {result.status_code}），稿件保留待重试')
    result=result.json()
    return dict(status='uploaded',repository=repository,path=path,url=result['content']['html_url'],commit=result['commit']['sha'])


def archive_edition(edition_path, review_path, queue, github, *, token=None):
    edition_path,review_path,queue=Path(edition_path),Path(review_path),Path(queue)
    review=read_json(review_path)
    required=['facts_checked','date_checked','dedup_checked','narration_checked']
    if (review.get('status')!='passed' or review.get('edition_sha256')!=sha256(edition_path)
        or any(review.get(k) is not True for k in required)):
        raise ValueError('稿件未完成审查或已变化，不能发布；review必须绑定当前edition SHA256')
    edition=validate_edition(read_json(edition_path));validate_date_proof(edition,edition_path.parent)
    day=edition['date'];text=public_markdown(edition)
    queue.mkdir(parents=True,exist_ok=True)
    draft=queue/f'{day}.md';draft.write_text(text,encoding='utf8')
    receipt=dict(date=day,markdown_file=draft.name,markdown_sha256=sha256(draft),
                 edition_sha256=sha256(edition_path),review_sha256=sha256(review_path),
                 status='pending_configuration',scope='reviewed_daily_markdown_only')
    token=credential_token() if token is None else token
    if github.get('repository') and token:
        try:receipt.update(push_markdown(github['repository'],day,text,token,branch=github.get('branch')))
        except (requests.RequestException,ValueError,RuntimeError) as exc:
            receipt.update(status='pending_retry',error_type=type(exc).__name__)
            # Never serialize request objects, headers, tokens or arbitrary exception text.
    write_json(queue/f'{day}.receipt.json',receipt)
    return receipt


def flush_queue(queue, github):
    queue=Path(queue);results=[];token=credential_token()
    for path in sorted(queue.glob('*.receipt.json')):
        receipt=read_json(path)
        if receipt.get('status') in {'uploaded','unchanged'}:continue
        filename=receipt.get('markdown_file','')
        if filename!=receipt['date']+'.md':raise ValueError('归档队列文件名无效')
        draft=queue/filename
        if sha256(draft)!=receipt['markdown_sha256']:raise ValueError('待上传新闻稿哈希变化，需重新审稿入队')
        if not github.get('repository') or not token:
            results.append(receipt);continue
        try:receipt.update(push_markdown(github['repository'],receipt['date'],draft.read_text('utf8'),token,branch=github.get('branch')))
        except (requests.RequestException,ValueError,RuntimeError) as exc:
            receipt.update(status='pending_retry',error_type=type(exc).__name__)
        write_json(path,receipt);results.append(receipt)
    return results
