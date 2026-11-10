"""Export a pointer into the standard issue layout without rendering media."""
import argparse
import json
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline.core import ROOT, read_json
from pipeline.issue_archive import export_issue, publish_current
from pipeline.storage import issue_paths, register_media, valid_day, data_root


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--date', required=True)
    parser.add_argument('--pointer', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--media', type=Path, action='append', default=[])
    parser.add_argument('--publish-current', action='store_true', help='Explicitly finalize reviewed output into an existing issue; preserve authoring inputs')
    args = parser.parse_args()
    from pipeline.updates import ensure_current
    if ensure_current(ROOT).get('rerun_required'):
        os.execv(sys.executable,[sys.executable,*sys.orig_argv[1:]])
    day = valid_day(args.date)
    output = args.output or issue_paths(day)['root']
    if args.media and (args.pointer or args.publish_current):
        parser.error('Use --media for original intake or --pointer for a sealed export in separate commands')
    if args.media and args.output:
        parser.error('--media uses the configured date storage; omit --output')
    if args.pointer or not args.media:
        default=issue_paths(day)['root']/'latest.json'
        if not default.is_file():default=data_root(ROOT)/'latest.json'
        if not default.is_file():default=ROOT/'outputs/daily/latest.json'
        pointer = read_json(args.pointer or default)
        if pointer.get('date') != day:
            raise ValueError('Requested date and pointer date disagree')
        result = publish_current(pointer, output) if args.publish_current else export_issue(pointer, output)
        print(json.dumps(dict(date=day, output=str(output.resolve()), files=len(result['files']),
                             **({'ledger':result['ledger']} if args.publish_current else {})), ensure_ascii=False))
    if args.media:
        # Media registration is for original intake, separate from sealed archives.
        if (output/'ISSUE_MANIFEST.json').exists():
            parser.error('Cannot add files to a sealed archive; register media before exporting into another directory')
        for media in args.media:
            print(register_media(day, media))


if __name__ == '__main__':
    main()
