"""Public framework-only export. No production media, voices, models or secrets."""
import argparse,json,shutil,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from pipeline.core import read_json,write_json,sha256
from pipeline.updates import _target

def build(output,root=ROOT):
    root=Path(root).resolve();output=Path(output).resolve()
    if output==root or root.is_relative_to(output):raise ValueError('Unsafe package destination')
    if output.exists() and any(output.iterdir()):raise FileExistsError(output)
    release=read_json(root/'architecture/release.json')
    output.mkdir(parents=True,exist_ok=True)
    for relative,expected in release['files'].items():
        source=_target(root,relative)
        if sha256(source)!=expected:raise ValueError('Release source changed: '+relative)
        dest=output/relative;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,dest)
    write_json(output/'architecture/release.json',release)
    write_json(output/'release.json',release)
    write_json(output/'config/pipeline.json',read_json(root/'config/pipeline.example.json'))
    write_json(output/'config/github.json',read_json(root/'config/github.example.json'))
    (output/'docs').mkdir(parents=True,exist_ok=True)
    (output/'docs/TODO.md').write_text('# 项目 TODO\n\n| ID | 范围 | 状态 | 验收 |\n|---|---|---|---|\n\n每期状态放data/issues/年份/刊期/tasks。\n',encoding='utf8')
    (output/'docs/CURRENT_PRODUCTION_REVIEW.md').write_text('公共架构/skill包：未在本机制作或验收新闻；生产素材需自行合法提供。\n',encoding='utf8')
    write_json(output/'FRAMEWORK_MANIFEST.json',dict(architecture_version=release['architecture_version'],skill_version=release['skill_version'],profile='public-framework-only',files={p.relative_to(output).as_posix():sha256(p) for p in output.rglob('*') if p.is_file()},excluded=['news media','music','voice audio','shared raster/IP assets','models','machine local config','tokens']))
    archive=output.parent/(output.name+'.zip')
    if archive.exists():raise FileExistsError(archive)
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as zipped:
        for p in output.rglob('*'):
            if p.is_file():zipped.write(p,output.name+'/'+p.relative_to(output).as_posix())
    return dict(directory=str(output),zip=str(archive),sha256=sha256(archive),bytes=archive.stat().st_size)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    print(json.dumps(build(parser.parse_args().output),ensure_ascii=False))
