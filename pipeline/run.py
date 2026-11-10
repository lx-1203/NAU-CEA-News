import argparse
import os
import sys
import shutil
from datetime import datetime
from pathlib import Path
from .core import ROOT, TZ, write_json, read_json
from .collect import collect
from .storage import issue_paths, data_root, record_task


def main():
    parser = argparse.ArgumentParser(description='njau-cea 每日新闻流水线')
    sub = parser.add_subparsers(dest='command', required=True)
    gather = sub.add_parser('collect')
    gather.add_argument('--date', default=datetime.now(TZ).date().isoformat())
    render = sub.add_parser('render')
    render.add_argument('--edition', type=Path, required=True)
    render.add_argument('--audio-manifest', type=Path, help='复用完整已核实配音清单，仅重剪素材与动作')
    render.add_argument('--archive', action='store_true', help='明确补制历史期；不得称为今日版')
    plan = sub.add_parser('plan', help='无需GPU：文稿自动配置素材与逐句表情动作')
    plan.add_argument('--edition', type=Path, required=True)
    plan.add_argument('--output', type=Path)
    archive = sub.add_parser('archive', help='上传已审新闻稿到公开GitHub；不上传视频或素材')
    archive.add_argument('--edition', type=Path)
    archive.add_argument('--review', type=Path)
    archive.add_argument('--retry-pending', action='store_true')
    args = parser.parse_args()
    from .updates import ensure_current
    update_receipt=ensure_current(ROOT)
    if update_receipt.get('rerun_required'):
        os.execv(sys.executable,[sys.executable,*sys.orig_argv[1:]])
    if args.command == 'archive':
        from .github_archive import archive_edition, flush_queue
        github_path=ROOT/'config/github.json'
        github=read_json(github_path) if github_path.exists() else {}
        queue=data_root(ROOT)/'publication-pending'
        if args.retry_pending:
            results=flush_queue(queue,github)
        else:
            if not args.edition or not args.review:parser.error('archive需要--edition和--review')
            results=[archive_edition(args.edition,args.review,queue,github)]
        for result in results:print(result['date']+': '+result['status']+' '+result.get('url',''))
        if any(r['status'] not in {'uploaded','unchanged'} for r in results):raise SystemExit(2)
        return
    if args.command == 'collect':
        output = issue_paths(args.date,root=ROOT,create=True)['editorial']/'candidates.json'
        result = collect(args.date, output)
        record_task(args.date,'collection','candidates_need_verification',root=ROOT,candidates=len(result['items']))
        print(f'{len(result["items"])} candidates: {output}')
        return
    if args.command == 'plan':
        from .production import production_plan
        output = args.output or issue_paths(read_json(args.edition)['date'],root=ROOT,create=True)['production']/'production-plan.json'
        write_json(output,production_plan(args.edition))
        record_task(read_json(args.edition)['date'],'planning','planned_requires_render',root=ROOT,plan=str(output))
        print(f'PLANNED: {output.resolve()}')
        return
    from .updates import production_guard
    with production_guard(ROOT,update_receipt):
        _render(args)


def _render(args):
    from .render import render_edition
    edition_path = args.edition.resolve()
    edition = read_json(edition_path)
    day = datetime.strptime(edition['date'], '%Y-%m-%d').date()
    from .date_guard import validate_issue_day
    validate_issue_day(edition['date'], archive=args.archive)
    if edition.get('archive_production') and not args.archive: raise ValueError('历史期必须明确传入 --archive')
    paths=issue_paths(day.isoformat(),root=ROOT,create=True)
    base = paths['root']
    lock = data_root(ROOT)/'.render.lock'
    fd = os.open(lock, os.O_CREAT|os.O_EXCL|os.O_WRONLY)
    run_dir = paths['runs']/datetime.now(TZ).strftime('run-%H%M%S-%f')
    try:
        os.write(fd, f'pid={os.getpid()}\nstarted={datetime.now(TZ).isoformat()}\nrun={run_dir}'.encode())
        result = render_edition(edition_path, run_dir, args.audio_manifest) if args.audio_manifest else render_edition(edition_path, run_dir)
        cue_dir=paths['audio_cues']/run_dir.name
        cue_dir.mkdir(parents=True,exist_ok=True)
        for cue in run_dir.glob('cue-*.wav'):
            if cue.stem[4:].isdigit():shutil.copy2(cue,cue_dir/cue.name)
        pointer = dict(date=edition['date'], run_dir=str(run_dir), edition=str(edition_path), video=str(run_dir/'news.mp4'), report=str(run_dir/'daily.html'), manifest=str(run_dir/'manifest.json'), status=result['status'])
        if (run_dir/'watch.html').is_file():
            pointer.update(player=str(run_dir/'watch.html'), chapters=str(run_dir/'chapters.json'))
        write_json(base/'latest.json', pointer)
        latest = data_root(ROOT)/'latest.json'
        if not latest.exists() or read_json(latest).get('date','') <= edition['date']:
            write_json(latest, pointer)
        print(f'RENDERED: {run_dir / "news.mp4"}', flush=True)
        record_task(edition['date'],'render','rendered_requires_final_review',root=ROOT,run_dir=str(run_dir),publication_status='not_published')
    except Exception as exc:
        write_json(base/'last-failure.json', dict(time=datetime.now(TZ).isoformat(), error=str(exc), run_dir=str(run_dir)))
        record_task(edition['date'],'render','failed',root=ROOT,error=str(exc),run_dir=str(run_dir))
        raise
    finally:
        os.close(fd)
        lock.unlink()


if __name__ == '__main__': main()
