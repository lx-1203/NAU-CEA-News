"""Install the canonical project skill with backups and local-edit protection."""
import argparse
import os
import shutil
import json
import hashlib
import sys
from datetime import datetime
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from pipeline.updates import _no_links, _atomic_write
def install(home, root=ROOT):
    root=Path(root).resolve()
    home=Path(home).expanduser().resolve();source=root/'skills/nau-cea-daily-video'
    dest=home/'skills/nau-cea-daily-video'
    _no_links(source);_no_links(dest)
    if not (source/'SKILL.md').is_file():raise ValueError('Missing canonical project skill')
    def sha(p):
        with p.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
    link=dest/'project-link.local.json'
    old=json.loads(link.read_text('utf8')) if link.is_file() else {}
    for relative,expected in old.get('installed_hashes',{}).items():
        p=dest/relative
        if not p.resolve().is_relative_to(dest):raise ValueError('Installed skill metadata escapes destination')
        _no_links(p)
        if not p.is_file() or sha(p)!=expected:raise ValueError('Installed skill has local edits; preserved: '+relative)
    files=[p for p in source.rglob('*') if p.is_file() and p.suffix!='.pyc' and not p.name.endswith('.local.json')]
    for p in files:_no_links(p)
    hashes={p.relative_to(source).as_posix():sha(p) for p in files}
    if old:
        for relative,expected in hashes.items():
            target=dest/relative
            _no_links(target)
            if relative not in old.get('installed_hashes',{}) and target.exists() and (not target.is_file() or sha(target)!=expected):
                raise ValueError('Unmanaged installed skill file conflicts; preserved: '+relative)
    if hashes==old.get('installed_hashes') and old.get('project_root')==str(root):
        print('SKILL CURRENT:',dest);return
    if dest.exists():
        backup=home/'skill-backups'/('nau-cea-daily-video-'+datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
        shutil.copytree(dest,backup)
    dest.mkdir(parents=True,exist_ok=True)
    previous={}
    try:
        for p in files:
            relative=p.relative_to(source)
            target=dest/relative;_no_links(target)
            previous[target]=target.read_bytes() if target.is_file() else None
            _atomic_write(target,p.read_bytes())
        _atomic_write(link,json.dumps(dict(project_root=str(root),installed_hashes=hashes),ensure_ascii=False,indent=2).encode('utf8'))
    except Exception:
        for target,content in previous.items():
            if content is None:target.unlink(missing_ok=True)
            else:_atomic_write(target,content)
        raise
    for stale in dest.rglob('SKILL.md'):
        if stale!=dest/'SKILL.md':stale.rename(stale.with_name('SKILL.md.retired-'+datetime.now().strftime('%Y%m%d%H%M%S')))
    entrypoints=list(dest.rglob('SKILL.md'))
    if entrypoints!=[dest/'SKILL.md']:raise ValueError('Extra old SKILL.md entries detected; preserved for manual consolidation')
    print('ONE SKILL INSTALLED:',dest/'SKILL.md')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--home',default=os.environ.get('CODEX_HOME',str(Path.home()/'.codex')))
    install(p.parse_args().home)
