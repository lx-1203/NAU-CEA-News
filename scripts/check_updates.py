"""Fail-closed use-before update gate. No cached-success mode."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline.updates import UpdateError, ensure_current


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--apply', action='store_true', help='Install a verified newer release')
    parser.add_argument('--offline', action='store_true', help='Inspection only; never reports current')
    args = parser.parse_args()
    try:
        result = ensure_current(args.root, apply=args.apply, offline=args.offline)
    except (UpdateError, OSError) as error:
        print(json.dumps({'status': 'error', 'error': str(error)}, ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 2 if result['status'] in {'available', 'offline'} else 0


if __name__ == '__main__':
    raise SystemExit(main())
