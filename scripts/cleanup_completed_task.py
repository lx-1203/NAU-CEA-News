"""Recycle explicitly retired task products after verifying their final manifest."""
import argparse,json,sys,os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scope',type=Path,required=True)
    parser.add_argument('--artifact-root',type=Path,required=True)
    parser.add_argument('--final-manifest',type=Path,required=True)
    parser.add_argument('--retire',type=Path,action='append',default=[])
    parser.add_argument('--protect',type=Path,action='append',default=[])
    parser.add_argument('--state',type=Path)
    args=parser.parse_args()
    from pipeline.updates import ensure_current,production_guard
    receipt=ensure_current(ROOT)
    if receipt.get('rerun_required'):os.execv(sys.executable,[sys.executable,*sys.orig_argv[1:]])
    from pipeline.cleanup import prepare_cleanup,execute_cleanup
    from pipeline.task_finish import retired_files
    from pipeline.storage import data_root
    scope=args.scope.absolute()
    retired=[p if p.is_absolute() else scope/p for p in args.retire]
    candidates,kept=retired_files(retired,scope=scope)
    protected=list(args.protect)
    for name in ['editorial','media','audio/source','review','assets','config','pipeline','scripts','skills','docs']:
        if (scope/name).exists():protected.append(scope/name)
    with production_guard(ROOT,receipt):
        state=prepare_cleanup(scope,args.artifact_root.absolute(),args.final_manifest.absolute(),candidates,protected_paths=protected,state_path=args.state.absolute() if args.state else None)
        result=execute_cleanup(state['state_path'],active_locks=[data_root()/'.render.lock',ROOT/'outputs/daily/.render.lock'])
    result['kept']=kept
    if kept:result['completed']=False
    print(json.dumps(result,ensure_ascii=False))
    return 0 if result['completed'] else 2

if __name__=='__main__':raise SystemExit(main())
