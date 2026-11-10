"""Create the immutable code archive and public-channel manifest after freeze."""
import argparse,json,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from pipeline.core import read_json,write_json,sha256
from pipeline.updates import _target

def build(root=ROOT,repository='lx-1203/NAU-CEA-News'):
    root=Path(root).resolve();release=read_json(root/'architecture/release.json')
    version=release['architecture_version'];target=root/'updates/update.zip'
    target.parent.mkdir(parents=True,exist_ok=True)
    for name,expected in release['files'].items():
        if sha256(_target(root,name))!=expected:raise ValueError('Managed file changed: '+name)
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
        for name in sorted(release['files']):
            info=zipfile.ZipInfo(name,date_time=(2026,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o100644<<16
            archive.writestr(info,(root/name).read_bytes())
    release['archive']=dict(url=f'https://raw.githubusercontent.com/{repository}/v{version}/updates/update.zip',sha256=sha256(target),bytes=target.stat().st_size)
    write_json(root/'architecture/release.json',release)
    write_json(root/'release.json',release)
    return dict(version=version,archive=str(target),archive_sha256=release['archive']['sha256'],archive_bytes=release['archive']['bytes'])

if __name__=='__main__':print(json.dumps(build(),ensure_ascii=False))
