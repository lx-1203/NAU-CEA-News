"""One date/category contract shared by CLI, desktop and downloaded projects."""
import os
import re
from datetime import date
from pathlib import Path
from .core import ROOT, TZ, read_json, write_json
from datetime import datetime


def valid_day(day):
    if not isinstance(day,str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',day):
        raise ValueError('刊期必须为 YYYY-MM-DD，不能包含路径')
    date.fromisoformat(day)
    return day


def data_root(root=ROOT):
    root=Path(root).resolve()
    local=root/'config/storage.local.json'
    configured=read_json(local).get('data_root') if local.is_file() else None
    value=os.environ.get('NJAU_CEA_DATA_ROOT') or configured or 'data'
    return (root/Path(value)).resolve()


def issue_paths(day,root=ROOT,create=False):
    day=valid_day(day)
    base=data_root(root)/'issues'/day[:4]/day
    result={'root':base,'editorial':base/'editorial','images':base/'media/images',
            'videos':base/'media/videos','evidence':base/'media/evidence',
            'audio_source':base/'audio/source','audio_cues':base/'audio/cues',
            'runs':base/'production/runs','production':base/'production',
            'deliverables':base/'deliverables/current','review':base/'review','tasks':base/'tasks'}
    if create:
        for path in result.values():path.mkdir(parents=True,exist_ok=True)
        task=result['tasks']/'status.json'
        if not task.exists():write_json(task,dict(date=day,status='prepared',tasks=[],publication_status='not_published'))
    return result


def classify_file(path):
    suffix=Path(path).suffix.lower()
    if suffix in {'.png','.jpg','.jpeg','.webp','.gif','.avif','.tif','.tiff','.bmp','.svg'}:return 'images'
    if suffix in {'.mp4','.mov','.webm','.mkv','.avi'}:return 'videos'
    return 'evidence'


def record_task(day,name,status,root=ROOT,**details):
    path=issue_paths(day,root,create=True)['tasks']/'status.json'
    current=read_json(path)
    tasks=current.get('tasks',[])
    if not isinstance(tasks,list):tasks=[]
    item=dict(task=name,status=status,updated_at=datetime.now(TZ).isoformat(),**details)
    tasks=[row for row in tasks if row.get('task')!=name]+[item]
    current.update(date=day,status=status,tasks=tasks)
    write_json(path,current)


def register_media(day,source,root=ROOT):
    """Copy a supplied original into this issue without overwriting unlike content."""
    import shutil
    from .core import sha256
    source=Path(source).resolve()
    if not source.is_file():raise FileNotFoundError(source)
    paths=issue_paths(day,root,create=True)
    group=classify_file(source)
    target=paths[group]/source.name
    digest=sha256(source)
    if target.exists() and sha256(target)!=digest:target=target.with_name(target.stem+'-'+digest[:12]+target.suffix)
    if not target.exists():shutil.copy2(source,target)
    return target
