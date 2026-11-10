"""Build a relocated, allowlisted project with current approved shared assets."""
import argparse, json, shutil, sys, zipfile
from collections import Counter
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from pipeline.core import read_json,write_json,sha256
from pipeline.portable import portable_config,new_edition
from pipeline.production import expression_assets


def build(output,include_issues=None):
    output=Path(output).resolve()
    if output==ROOT or output.is_relative_to(ROOT/'assets'):raise ValueError('Export overlaps source assets')
    if output.exists() and any(output.iterdir()):raise FileExistsError('Export destination must be empty')
    output.mkdir(parents=True,exist_ok=True)
    assets=[]
    def copy(source,relative,group=None):
        source=Path(source);dest=output/relative
        if not dest.resolve().is_relative_to(output):raise ValueError('Export path escapes bundle')
        dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,dest)
        if group:assets.append(dict(path=dest.relative_to(output).as_posix(),sha256=sha256(dest),bytes=dest.stat().st_size,group=group,acceptance='current_approved_original',redistribution='upstream/IP rights retained; local handoff is not a public license'))
    release=read_json(ROOT/'architecture/release.json')
    for relative in release['files']:copy(ROOT/relative,relative)
    copy(ROOT/'architecture/release.json','architecture/release.json')
    for name in ['news-player.css','news-player.js']:copy(ROOT/'assets/player'/name,'assets/player/'+name)
    source=read_json(ROOT/'config/pipeline.json')
    config=portable_config(source,output)
    def relative_paths(value):
        if isinstance(value,dict):return {k:relative_paths(v) for k,v in value.items()}
        if isinstance(value,list):return [relative_paths(v) for v in value]
        if isinstance(value,str) and value.startswith(str(output)):return '.'+value[len(str(output)):]
        return value
    write_json(output/'config/pipeline.json',relative_paths(config))
    write_json(output/'config/github.json',read_json(ROOT/'config/github.example.json'))
    (output/'docs/TODO.md').write_text('# 项目 TODO\n\n完成事项先保存当期review证据，再移除行。每期详细状态见data/issues/YYYY/YYYY-MM-DD/tasks/status.json。\n\n| ID | 优先级 | 负责人 | 范围 | 状态 | 验收与下一步 |\n|---|---|---|---|---|---|\n',encoding='utf8')
    (output/'docs/CURRENT_PRODUCTION_REVIEW.md').write_text('这是新电脑复用包，没有在该电脑完成整期制作验收。历史样例见data/issues各日期的review与ISSUE_MANIFEST.json；新一期必须实际核验，不把本包存在视为生产通过。\n',encoding='utf8')
    for anchor,poses in expression_assets().items():
        for pose,path in poses.items():copy(path,path.relative_to(ROOT),'anchor_'+anchor)
    for name in ['njau-emblem-official.png','cea-emblem.png','njau-cea-news-raster.png','naucea-screen-loop.mp4']:
        copy(ROOT/'assets/branding'/name,'assets/branding/'+name,'branding')
    demo=ROOT/'assets/audio/voice-demo.wav'
    if demo.is_file():copy(demo,'assets/audio/voice-demo.wav','voice_demo_local_only')
    demo_script=ROOT/'assets/audio/voice-demo-data.js'
    if demo_script.is_file():copy(demo_script,'assets/audio/voice-demo-data.js','voice_demo_local_only')
    for anchor,voice in source['speech']['workbench']['voices'].items():
        path=ROOT/voice['reference']
        if sha256(path)!=voice['sha256']:raise ValueError('Frozen voice hash changed: '+anchor)
        copy(path,f'assets/voices/{anchor}/reference.wav','voice_'+anchor)
    if source.get('opening',{}).get('enabled'):
        approved=Path(source['opening']['approval']);approval=read_json(approved)
        for field in ['video','silent_video','credits_file']:
            path=approved.parent/approval[field]
            if field!='credits_file' and sha256(path)!=approval[field+'_sha256']:raise ValueError('Approved opening changed')
            name=field+path.suffix
            copy(path,'assets/opening/'+name,'opening');approval[field]=name
        write_json(output/'assets/opening/APPROVED.json',approval)
    library=ROOT/'assets/transitions/campus-ip-sweep-v4/library.json';data=read_json(library)
    for item in data['items']:
        for field,key in [('webm','sha256'),('art','art_sha256'),('reference','reference_sha256'),('character','character_sha256'),('preview',None)]:
            if not item.get(field):continue
            path=library.parent/item[field]
            if key and item.get(key) and sha256(path)!=item[key]:raise ValueError('Transition changed: '+item['id'])
            copy(path,Path('assets/transitions/campus-ip-sweep-v4')/item[field],'transition_'+field)
        item.pop('mov',None)
    data['bundle_note']='Current v4 transparent WebM and original art; optional ProRes MOV not included.'
    write_json(output/'assets/transitions/campus-ip-sweep-v4/library.json',data)
    for folder,name in [('generated','provenance.json'),('gestures-v2','sources.json')]:
        p=ROOT/f'assets/characters/anchors/{folder}/{name}'
        if p.exists():copy(p,p.relative_to(ROOT))
    for relative in ['assets/references/mascots.png','assets/references/editorial/HANDOFF.md','assets/references/editorial/sample-20261107.html']:
        path=ROOT/relative
        if path.exists():copy(path,relative,'reference')
    write_json(output/'examples/edition.empty-template.json',new_edition('2026-11-10'))
    write_json(output/'examples/editorial-review.example.json',dict(status='not_reviewed',edition_sha256='',facts_checked=False,date_checked=False,dedup_checked=False,narration_checked=False))
    if include_issues:
        source_issues=Path(include_issues)/'issues'
        if source_issues.exists():shutil.copytree(source_issues,output/'data/issues')
        index=Path(include_issues)/'index.html'
        if index.exists():copy(index,'data/index.html')
    write_json(output/'assets/qualified-assets.json',dict(version=2,items=assets,rights='Third-party assets keep their original rights; this package is a local reuse handoff, not an unrestricted public redistribution license.'))
    # Default update source is live HTTPS; no implicit local-baseline channel.
    files={p.relative_to(output).as_posix():sha256(p) for p in output.rglob('*') if p.is_file()}
    write_json(output/'BUNDLE_MANIFEST.json',dict(version=2,architecture_version=release['architecture_version'],skill_version=release['skill_version'],profile='windows-relocatable-local-reuse',files=files,asset_groups=dict(Counter(a['group'] for a in assets)),mutable_after_install=['config/pipeline.json','config/github.json','config/*.local.json','data/**','runtime/**'],not_tested='Fresh Windows installation, full model download and GPU speech synthesis.'))
    archive=output.parent/(output.name+'.zip')
    if archive.exists():raise FileExistsError(archive)
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=5) as zipped:
        for path in output.rglob('*'):
            if path.is_file():zipped.write(path,output.name+'/'+path.relative_to(output).as_posix())
    result=dict(directory=str(output),zip=str(archive),sha256=sha256(archive),bytes=archive.stat().st_size,assets=len(assets))
    print(json.dumps(result,ensure_ascii=False));return result

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);parser.add_argument('--include-issues',type=Path)
    args=parser.parse_args();build(args.output,args.include_issues)
