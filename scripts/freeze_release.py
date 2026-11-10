"""Hash the explicit managed list; never publish local data or credentials."""
import argparse, json, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from pipeline.core import read_json,write_json,sha256
from pipeline.updates import _target,_version,UpdateError

def freeze(root,architecture_version,skill_version):
    root=Path(root).resolve();_version(architecture_version);_version(skill_version)
    names=read_json(root/'architecture/managed-files.json')['files']
    hashes={name:sha256(_target(root,name)) for name in names}
    result=dict(project='njau-cea-news',architecture_version=architecture_version,skill_version=skill_version,files=hashes)
    path=root/'architecture/release.json'
    if path.exists():
        old=read_json(path)
        if (_version(architecture_version)<_version(old['architecture_version']) or _version(skill_version)<_version(old['skill_version'])):raise UpdateError('Release version cannot go backwards')
        changed={name for name in hashes.keys() | old['files'].keys() if hashes.get(name)!=old['files'].get(name)}
        if changed and architecture_version==old['architecture_version']:
            raise UpdateError('Changed managed files require a higher architecture version')
        if any(name.startswith('skills/nau-cea-daily-video/') for name in changed) and skill_version==old['skill_version']:
            raise UpdateError('Changed skill files require a higher skill version')
    write_json(path,result);return result

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--architecture-version',required=True);parser.add_argument('--skill-version',required=True)
    args=parser.parse_args();r=freeze(ROOT,args.architecture_version,args.skill_version)
    print(json.dumps(dict(architecture_version=r['architecture_version'],skill_version=r['skill_version'],managed_files=len(r['files']))))
