"""Check/update music, inspect rotation, mix one video, or reclaim owned cache."""
import argparse
import json
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from pipeline.bgm import BgmSession,Rotation,_ffmpeg,_save,clean_cache,music_directory,music_lock,settings
from pipeline.bgm_source import refresh_catalog


def main():
    parser=argparse.ArgumentParser(description='NJAU-CEA BGM: live update, no-repeat cycles, zero retained audio cache')
    parser.add_argument('--root',type=Path,default=ROOT)
    commands=parser.add_subparsers(dest='command',required=True)
    commands.add_parser('check',help='Check live GitHub catalog; download metadata only')
    commands.add_parser('status',help='Inspect persistent local rotation without downloading audio')
    commands.add_parser('cleanup',help='Delete only re-downloadable files in this tool-owned cache')
    mix=commands.add_parser('mix',help='Automatically select, download, mix, validate, record, and clean up')
    mix.add_argument('--date',required=True)
    mix.add_argument('--input',type=Path,required=True)
    mix.add_argument('--output',type=Path,required=True)
    mix.add_argument('--timeline',type=Path,required=True,help='Actual opening and silent-interlude intervals')
    args=parser.parse_args();root=args.root.resolve();directory=music_directory(root)
    if args.command=='mix':
        timeline=json.loads(args.timeline.read_text(encoding='utf-8-sig'))
        receipt=args.output.with_suffix('.bgm.json')
        if args.output.exists() or receipt.exists():raise FileExistsError('Output or receipt already exists')
        with BgmSession(root,args.date) as session:
            session.mix(args.input,args.output,timeline)
            _ffmpeg(['-xerror','-i',args.output,'-f','null','-'])
            session.seal_cache()
            from pipeline.core import sha256
            value=dict(session.receipt,status='validated',video_sha256=sha256(args.output),cleanup=session.cleanup_receipt)
            _save(receipt,value)
            session.commit(args.output)
        print(json.dumps(dict(output=str(args.output.resolve()),receipt=str(receipt.resolve()),
                             title=value['selection']['track']['title'],cycle=value['selection']['cycle'],
                             cleanup=value['cleanup']),ensure_ascii=False))
        return
    with music_lock(directory):
        if args.command=='cleanup':value=clean_cache(directory/'cache')
        elif args.command=='check':
            catalog=refresh_catalog(settings(root));_save(directory/'catalog.json',catalog)
            value=dict(published_version=catalog['version'],channel_version=catalog['channel_version'],
                       tracks=len(catalog['tracks']),audio_downloaded=False)
        else:
            path=directory/'catalog.json'
            if not path.exists():
                value=dict(status='not_initialized',next_command='python scripts/bgm.py check',history=str(directory/'history.json'))
            else:
                rotation=Rotation(directory,json.loads(path.read_text(encoding='utf-8-sig')))
                state=rotation.status()
                value=dict(cycle=state['cycle'],eligible_tracks=state['eligible_tracks'],
                           used_in_cycle=len(state['used']),remaining=state['remaining_in_cycle'],
                           committed_editions=len(state['assignments']),history=str(rotation.path),
                           last_sha256=state['last_sha256'],pending=state['pending'])
    print(json.dumps(value,ensure_ascii=False))


if __name__=='__main__':main()
