"""Pinned Windows workbench installation, run only by the explicit setup action."""
import argparse
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def sha(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()

def download(url,path,digest):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists():
        if sha(path)!=digest:raise ValueError('Existing file hash differs: '+str(path))
        return path
    part=path.with_suffix(path.suffix+'.part');offset=part.stat().st_size if part.exists() else 0
    request=urllib.request.Request(url,headers={'User-Agent':'NAU-CEA-Reuse','Range':f'bytes={offset}-'} if offset else {'User-Agent':'NAU-CEA-Reuse'})
    with urllib.request.urlopen(request,timeout=90) as response:
        mode='ab' if offset and response.status==206 else 'wb'
        with part.open(mode) as stream:shutil.copyfileobj(response,stream,1024*1024)
    if sha(part)!=digest:
        failed=part.with_name(part.name+'.bad-'+sha(part)[:12])
        if not failed.exists():part.rename(failed)
        raise ValueError('Downloaded file hash differs; failed file retained: '+str(failed))
    part.replace(path);return path

def extract_safe(archive,target):
    target=Path(target).resolve();target.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(archive) as z:
        for member in z.infolist():
            dest=(target/member.filename).resolve()
            if not dest.is_relative_to(target) or stat.S_ISLNK(member.external_attr>>16):raise ValueError('Unsafe archive member')
        z.extractall(target)

def run(args,**kwargs):
    print('Running: '+str(args[0]),flush=True)
    subprocess.run([str(a) for a in args],check=True,**kwargs)

def install(uv,plan_only=False):
    manifest=json.loads((ROOT/'config/reuse-components.json').read_text('utf8'))
    runtime=ROOT/'runtime';studio=runtime/'IndexTTS2-Studio';cache=runtime/'downloads'
    if plan_only:
        print(json.dumps(dict(base=manifest['downloads']['studio'],patch=manifest['downloads']['patch'],
            model_files=len(manifest['models']),model_bytes=sum(m['size'] for m in manifest['models']),target=str(studio)),indent=2));return
    if not (ROOT/'config/pipeline.json').is_file():raise ValueError('Project configuration missing')
    base=manifest['downloads']['studio']
    base_zip=download(base['url'],cache/'studio.zip',base['sha256'])
    if not studio.exists():
        source=runtime/'studio-source';extract_safe(base_zip,source)
        candidates=[p.parent for p in source.glob('*/server.py') if (p.parent/'pyproject.toml').exists()]
        if len(candidates)!=1:raise ValueError('Pinned studio archive layout changed')
        shutil.copytree(candidates[0],studio)
        (studio/'.nau-base-revision').write_text(base['version'],encoding='utf8')
    elif not (studio/'.nau-base-revision').exists() or (studio/'.nau-base-revision').read_text('utf8')!=base['version']:
        raise ValueError('Existing runtime is not this pinned installation; preserved unchanged')
    git=manifest['downloads']['git'];git_dir=runtime/'mingit'
    if not (git_dir/'cmd/git.exe').exists():extract_safe(download(git['url'],cache/'mingit.zip',git['sha256']),git_dir)
    os.environ['PATH']=str(git_dir/'cmd')+os.pathsep+os.environ.get('PATH','')
    python=studio/'.venv/Scripts/python.exe'
    if not python.exists():run([uv,'venv','--python','3.11',studio/'.venv'])
    run([uv,'pip','install','--python',python,'torch==2.8.0+cu128','torchaudio==2.8.0+cu128','--index-url','https://download.pytorch.org/whl/cu128'])
    run([uv,'pip','install','--python',python,'--no-deps','-r',ROOT/'config/workbench-requirements.lock.txt'])
    run([uv,'pip','install','--python',python,'--no-deps','-e',studio])
    run([uv,'pip','check','--python',python])
    patch=manifest['downloads']['patch'];patch_dir=runtime/'workbench-patch-v033'
    extract_safe(download(patch['url'],cache/'workbench-patch-v033.zip',patch['sha256']),patch_dir)
    installers=[p for p in patch_dir.rglob('install.py') if (p.parent/'payload').is_dir()]
    if len(installers)!=1:raise ValueError('Workbench patch installer layout changed')
    run([python,installers[0],'--target',studio])
    for i,item in enumerate(manifest['models'],1):
        target=(studio/'checkpoints'/item['target']).resolve()
        if not target.is_relative_to(studio/'checkpoints'):raise ValueError('Model target escapes checkpoints')
        print(f'Model file {i}/{len(manifest["models"])}: {item["target"]}',flush=True)
        download(item['url'],target,item['sha'])
    # Only required text-processing data; downloaded into this installation's cache.
    env=dict(os.environ,NLTK_DATA=str(runtime/'cache/nltk'))
    run([python,'-c',"import nltk; [nltk.download(x,raise_on_error=True) for x in ['averaged_perceptron_tagger_eng','averaged_perceptron_tagger','cmudict','punkt_tab']]"],env=env)
    run([python,'-c','import torch; print("CUDA ready:",torch.cuda.is_available())'])
    (runtime/'workbench-installed.json').write_text(json.dumps(dict(base=base['version'],patch=patch['version'],models=len(manifest['models']))),encoding='utf8')
    print('Workbench installed. First synthesis still requires a voice smoke test.')

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--uv',default=str(ROOT/'.tools/uv/uv.exe'));parser.add_argument('--plan-only',action='store_true')
    args=parser.parse_args();install(args.uv,args.plan_only)
