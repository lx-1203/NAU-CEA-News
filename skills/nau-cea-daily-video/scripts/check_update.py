"""Check the actual release source, then synchronize this installed skill."""
import argparse, json, subprocess, sys
from pathlib import Path
skill=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser();parser.add_argument('--project',type=Path)
args=parser.parse_args()
link=skill/'project-link.local.json'
root=args.project
if root is None and (Path.cwd()/'architecture/release.json').is_file():root=Path.cwd()
if root is None and link.is_file():root=Path(json.loads(link.read_text('utf8'))['project_root'])
if root is None:raise SystemExit('Pass --project pointing to an NJAU-CEA project.')
root=root.resolve()
subprocess.run([sys.executable,str(root/'scripts/check_updates.py'),'--apply'],check=True,cwd=root)
if link.is_file():
    subprocess.run([sys.executable,str(root/'scripts/install_agent_skill.py'),'--home',str(skill.parents[1])],check=True,cwd=root)
