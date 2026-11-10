"""Finalize a reviewed issue, then recycle explicitly retired generated output."""
import json,os
from pathlib import Path
from .core import ROOT,read_json,write_json,sha256
from .storage import valid_day,record_task,data_root
from .issue_archive import publish_current,verify_issue,_guard_archive_path
from .cleanup import prepare_cleanup,execute_cleanup


def register_intermediates(run_dir,day,paths):
    run=_guard_archive_path(run_dir)
    entries=[]
    for raw in dict.fromkeys(paths):
        path=_guard_archive_path(raw)
        if not path.is_relative_to(run) or path==run:raise ValueError('Intermediate escapes producer run')
        if path.is_file():entries.append(dict(path=path.relative_to(run).as_posix(),sha256=sha256(path),bytes=path.stat().st_size,role='generated_intermediate'))
    write_json(run/'cleanup-candidates.json',dict(schema=1,date=valid_day(day),branch='primary_broadcast',files=entries))


def retired_files(paths,scope=None):
    """Expand only explicitly retired groups; never follow directory redirects."""
    files=[];kept=[]
    for raw in paths:
        try:
            path=_guard_archive_path(raw)
            if scope is not None and (path==scope or not path.is_relative_to(scope)):
                raise ValueError('Retired group must be strictly inside this task scope')
            if not path.exists():continue
            if path.is_file():files.append(path);continue
            for folder,dirs,names in os.walk(path,followlinks=False):
                safe=[]
                for name in dirs:
                    try:_guard_archive_path(Path(folder)/name);safe.append(name)
                    except ValueError:kept.append(dict(path=str(Path(folder)/name),reason='reparse point retained'))
                dirs[:]=safe
                for name in names:
                    try:files.append(_guard_archive_path(Path(folder)/name))
                    except ValueError:kept.append(dict(path=str(Path(folder)/name),reason='reparse point retained'))
        except ValueError as error:kept.append(dict(path=str(raw),reason=str(error)))
    return files,kept


def _input_references(root,extra_paths=()):
    protected=[];visited=set()
    def visit(path,reference_base=None):
        path=path.resolve()
        base=Path(reference_base).resolve() if reference_base else path.parent
        if (path,base) in visited or not path.is_file():return
        visited.add((path,base))
        protected.append(path)
        try:value=read_json(path)
        except (ValueError,OSError):return
        def walk(value):
            if isinstance(value,list):
                for item in value:walk(item)
            elif isinstance(value,dict):
                for key,item in value.items():
                    if key in {'path','audio_manifest','edition'} and isinstance(item,str) and not item.startswith(('http:','https:','data:')):
                        candidate=(base/item).resolve()
                        if candidate.is_file() and candidate.is_relative_to(root):
                            protected.append(candidate)
                            if candidate.suffix=='.json':visit(candidate,base if key=='audio_manifest' else None)
                    elif key in {'audio_inputs','source_hashes'} and isinstance(item,dict):
                        for name in item:
                            candidate=((ROOT if key=='source_hashes' else path.parent)/name).resolve()
                            if candidate.is_file() and candidate.is_relative_to(root):protected.append(candidate)
                    else:walk(item)
        walk(value)
    editorial=root/'editorial'
    if editorial.is_dir():
        for path in editorial.glob('*.json'):visit(path)
    for raw in extra_paths:
        if raw:visit(Path(raw))
    runs=root/'production/runs'
    if runs.is_dir():
        for run in runs.iterdir():
            try:_guard_archive_path(run)
            except ValueError:continue
            for name in ['edition.json','production-plan.json','manifest.json']:visit(run/name)
    return protected


def finish_reviewed_issue(pointer,target_issue,recycler=None,active_locks=()):
    """Caller has reviewed the output; do not clean if finalization fails."""
    root=_guard_archive_path(target_issue)
    result=publish_current(pointer,root)
    verify_issue(root,result['ledger'])
    tasks=root/'tasks';tasks.mkdir(exist_ok=True)
    queue_path=tasks/'cleanup-queue.json'
    queue=read_json(queue_path) if queue_path.is_file() else dict(retired_paths=[])
    retired=list(queue['retired_paths']);kept=[]
    if result['previous_current']:retired.append(str(root/result['previous_current']))
    source_run=Path(pointer.get('run_dir') or Path(pointer['video']).parent)
    protected=_input_references(root,[pointer.get('edition',source_run/'edition.json'),pointer.get('manifest',source_run/'manifest.json'),pointer.get('source_render_manifest')])
    for name in ['editorial','media','audio/source','review']:
        if (root/name).exists():protected.append(root/name)
    runs=root/'production/runs'
    if runs.is_dir():
        for run in runs.iterdir():
            try:
                _guard_archive_path(run)
                registry=run/'cleanup-candidates.json';manifest=run/'manifest.json'
                if not registry.is_file() or not manifest.is_file():continue
                record=read_json(registry);built=read_json(manifest)
                if (record.get('date')!=pointer['date'] or record.get('branch')!='primary_broadcast'
                    or built.get('date')!=pointer['date'] or built.get('status')!='rendered'
                    or built.get('files',{}).get(registry.name)!=sha256(registry)):
                    raise ValueError('Producer registry is not bound to a successful matching render')
                for name in built.get('audio_inputs',{}):
                    candidate=Path(name)
                    if candidate.is_file() and candidate.resolve().is_relative_to(root):protected.append(candidate.resolve())
                for item in record['files']:
                    path=_guard_archive_path(run/item['path'])
                    if not path.is_relative_to(run) or item.get('role')!='generated_intermediate':raise ValueError('Invalid producer artifact')
                    if not path.exists():continue
                    if built['files'].get(item['path'])!=item['sha256'] or sha256(path)!=item['sha256']:
                        kept.append(dict(path=str(path),reason='Producer artifact changed; retained'));continue
                    if any(path==p or p in path.parents for p in protected):
                        kept.append(dict(path=str(path),reason='Active authoring/source dependency retained',kind='dependency'));continue
                    retired.append(str(path))
            except (ValueError,OSError,KeyError,TypeError) as error:kept.append(dict(path=str(run),reason=str(error)))
    queue['retired_paths']=list(dict.fromkeys(retired));write_json(queue_path,queue)
    # Current entry points must not lead to a retired construction directory.
    current=root/'deliverables/current'
    latest=dict(date=pointer['date'],run_dir=str(current),video=str(current/'news.mp4'),player=str(current/'watch.html'),report=str(current/'daily.html'),edition=str(current/'edition.json'),manifest=str(root/result['ledger']),status='ready_for_user_review')
    write_json(root/'latest.json',latest)
    if root.is_relative_to(data_root()):
        global_latest=data_root()/'latest.json'
        if not global_latest.exists() or read_json(global_latest).get('date','')<=pointer['date']:write_json(global_latest,latest)
    candidates,skipped=retired_files(queue['retired_paths'],scope=root);kept.extend(skipped)
    # Filter original/active sources before planning; those are deliberately kept.
    candidates=[p for p in candidates if not any(p==q or q in p.parents for q in protected)]
    try:
        state=prepare_cleanup(root,root,root/result['ledger'],candidates,protected_paths=protected,state_path=tasks/'cleanup-state.json')
        cleanup=execute_cleanup(state['state_path'],recycler=recycler,active_locks=active_locks)
        verify_issue(root,result['ledger'])
    except (ValueError,OSError) as error:cleanup=dict(status='blocked',completed=False,count=0,moved_bytes=0,reason=str(error))
    cleanup['kept']=kept
    if any(item.get('kind')!='dependency' for item in kept):cleanup['completed']=False
    result.update(cleanup=cleanup,completion_status='complete' if cleanup.get('completed') else 'pending_cleanup')
    write_json(tasks/'completion.json',dict(date=pointer['date'],status=result['completion_status'],ledger=result['ledger'],cleanup=cleanup))
    status_path=tasks/'status.json'
    if status_path.is_file():
        try:status=read_json(status_path)
        except (ValueError,OSError):status=None
        if isinstance(status,dict):
            status.update(status=result['completion_status'],cleanup_state=str(tasks/'cleanup-state.json'),finalization_ledger=result['ledger'])
            write_json(status_path,status)
    return result
