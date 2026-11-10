"""Explicit, verified cleanup plans. Recyclers return per-file success receipts.

An injected recycler receives a list of absolute filenames and returns a list of
{path, status, reason?} objects. Only status='recycled' is a success receipt.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
from contextlib import contextmanager


def _path(value):
    path = Path(value)
    if not path.is_absolute():
        raise ValueError(f'Absolute path required: {path}')
    path = Path(os.path.abspath(path))
    if os.name == 'nt' and any(':' in part for part in path.parts[1:]):
        raise ValueError(f'Alternate data streams forbidden: {path}')
    for item in [*reversed(path.parents), path]:
        try:
            stat = item.lstat()
        except FileNotFoundError:
            continue
        if item.is_symlink() or getattr(stat, 'st_file_attributes', 0) & 0x400:
            raise ValueError(f'Reparse point forbidden: {item}')
    return path


def _inside(value, root):
    path = _path(value if Path(value).is_absolute() else root / value)
    if path == root or root not in path.parents:
        raise ValueError(f'Path must be strictly inside scope: {path}')
    return path


def _snapshot(path):
    path = _path(path)
    if not path.is_file():
        raise ValueError(f'Missing regular file: {path}')
    before = path.stat()
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ValueError(f'File changed while reading: {path}')
    return {'sha256': digest.hexdigest(), 'bytes': after.st_size, 'mtime_ns': after.st_mtime_ns}


def _protected(paths):
    result = {}
    for raw in paths:
        path = _path(raw)
        if path.is_dir():
            members = _members(path)
            result.update((member, _snapshot(member)) for member in members)
            result[str(path)] = {'members': members}
        else:
            result[str(path)] = _snapshot(path)
    return result


def _members(path):
    members = []
    if not _path(path).is_dir():
        raise ValueError(f'Missing protected directory: {path}')
    # os.walk never follows symlinks; _path rejects Windows junctions too.
    for folder, dirs, files in os.walk(_path(path), followlinks=False):
        dirs[:] = sorted(d for d in dirs if _safe_child(Path(folder) / d))
        members.extend(str(_path(Path(folder) / name)) for name in files)
    return sorted(members)


def _safe_child(path):
    try:
        _path(path)
        return True
    except ValueError:
        return False


def _verify(protected, full=True):
    for name, expected in protected.items():
        if 'members' in expected:
            current = {'members': _members(name)}
            target = expected
        elif full:
            current, target = _snapshot(name), expected
        else:
            stat = _path(name).stat()
            current = {'bytes': stat.st_size, 'mtime_ns': stat.st_mtime_ns}
            target = {key: expected[key] for key in current}
        if current != target:
            raise ValueError(f'Protected file changed: {name}')


def _write(path, data):
    _path(path)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w',encoding='utf8',prefix=path.name+'.',suffix='.tmp',dir=path.parent,delete=False) as stream:
            temporary=Path(stream.name)
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        _path(path)
        os.replace(temporary, path)
    finally:
        if temporary and temporary.exists():_path(temporary).unlink()


def _log(path, event):
    with path.open('a', encoding='utf8') as stream:
        stream.write(json.dumps(event, ensure_ascii=False) + '\n')
        stream.flush()
        os.fsync(stream.fileno())


def _metadata_safe(state_path,log_path,protected):
    metadata=[state_path,log_path,state_path.with_name(state_path.name+'.lock')]
    for raw in protected:
        path=_path(raw)
        for meta in metadata:
            if meta==path or path in meta.parents or meta in path.parents:
                raise ValueError('Cleanup metadata overlaps a protected final/dependency')


@contextmanager
def _lock(state_path):
    lock = _path(state_path.with_name(state_path.name + '.lock'))
    descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        os.write(descriptor, str(os.getpid()).encode('ascii'))
        yield
    finally:
        os.close(descriptor)
        lock.unlink()


def prepare_cleanup(scope, artifact_root, final_manifest, retired_paths,
                    protected_paths=(), state_path=None):
    """Validate the final manifest and register ONLY explicitly retired files."""
    scope, artifact_root = _path(scope), _path(artifact_root)
    if scope.parent==scope:raise ValueError('Filesystem root cannot be a cleanup scope')
    if not scope.is_dir() or not artifact_root.is_dir():
        raise ValueError('Scope and artifact_root must be existing physical directories')
    state_path = _inside(state_path or scope / '.cleanup-state.json', scope)
    log_path = _inside(state_path.with_name('cleanup-log.jsonl'), scope)
    manifest_path = None
    if isinstance(final_manifest, dict):
        manifest = final_manifest
    else:
        manifest_path = _path(final_manifest)
        manifest = json.loads(manifest_path.read_text(encoding='utf-8-sig'))
    files = manifest.get('files')
    if not isinstance(files, dict) or not files:
        raise ValueError('Final manifest must contain a nonempty files mapping')
    critical = []
    for relative, expected in files.items():
        final = _inside(relative, artifact_root)
        actual = _snapshot(final)
        expected = {'sha256': expected} if isinstance(expected, str) else expected
        if not isinstance(expected, dict) or actual['sha256'] != expected.get('sha256'):
            raise ValueError(f'Final manifest hash mismatch: {final}')
        if 'bytes' in expected and actual['bytes'] != expected['bytes']:
            raise ValueError(f'Final manifest size mismatch: {final}')
        critical.append(final)
    critical.extend(_path(p if Path(p).is_absolute() else scope / p) for p in protected_paths)
    if manifest_path:
        critical.append(manifest_path)
    protected = _protected(critical)
    _metadata_safe(state_path,log_path,protected)
    state = {'scope': str(scope), 'artifact_root': str(artifact_root),
             'state_path': str(state_path), 'log_path': str(log_path),
             'protected': protected, 'candidates': [], 'skipped': []}
    excluded = {state_path, log_path, state_path.with_name(state_path.name + '.lock'),
                state_path.with_name(state_path.name + '.tmp')}
    seen = set()
    for raw in retired_paths:
        try:
            candidate = _inside(raw, scope)
            if candidate in seen:
                continue
            seen.add(candidate)
            if candidate in excluded or any(candidate == Path(p) or Path(p) in candidate.parents
                                             for p in protected):
                raise ValueError('Protected final, dependency, or cleanup metadata')
            snapshot = _snapshot(candidate)
            state['candidates'].append({'path': str(candidate), **snapshot,
                                        'reason': 'explicitly retired by completed task'})
        except (ValueError, OSError) as error:
            state['skipped'].append({'path': str(raw), 'reason': str(error)})
    state['candidates'].sort(key=lambda item: item['path'])
    state_path.parent.mkdir(parents=True, exist_ok=True)
    _path(state_path.parent)
    with _lock(state_path):
        _verify(protected)
        _write(state_path, state)
        _log(log_path, {'event': 'plan', 'candidates': len(state['candidates']),
                        'bytes': sum(x['bytes'] for x in state['candidates']), 'skipped': state['skipped']})
    return state


def _completed(log):
    receipts = set()
    if log.exists():
        with log.open(encoding='utf8') as stream:
            for line in stream:
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue  # Interrupted last append is never a success receipt.
                if event.get('event') == 'recycled':
                    receipts.add((event['path'], event.get('sha256'), event.get('mtime_ns')))
    return receipts


def _native_recycle(paths, scope):
    if os.name != 'nt':
        raise OSError('Windows Recycle Bin is required; no permanent-delete fallback')
    script = Path(__file__).resolve().parent.parent / 'scripts' / 'recycle_files.ps1'
    with tempfile.TemporaryDirectory(prefix='cleanup-request-') as temporary:
        request = Path(temporary) / 'request.json'
        request.write_text(json.dumps({'scope': str(scope), 'paths': paths}), encoding='utf8')
        command = ['powershell.exe', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File',
                   str(script), '-InputFile', str(request)]
        output = subprocess.run(command, capture_output=True, text=True, encoding='utf8', check=True)
        return json.loads(output.stdout.lstrip('\ufeff'))


def execute_cleanup(state_path, recycler=None, active_locks=()):
    """Recycle unchanged candidates; a failure never falls back to deletion.

    active_locks is a collection of lock file paths, checked before every file.
    moved_bytes reports bytes moved into the bin, never disk space released.
    """
    state_path = _path(state_path)
    state = json.loads(state_path.read_text(encoding='utf8'))
    scope = _path(state['scope'])
    _inside(state_path, scope)
    log = _inside(state['log_path'], scope)
    _metadata_safe(state_path,log,state['protected'])
    metadata = {state_path, log, state_path.with_name(state_path.name + '.lock'),
                state_path.with_name(state_path.name + '.tmp')}
    result = {'status': 'ok', 'count': 0, 'moved_bytes': 0,
              'freed_bytes': None, 'skipped': list(state.get('skipped',[])), 'state_path': str(state_path)}

    def guard(full=False):
        if any(Path(lock).exists() for lock in active_locks):
            raise ValueError('Active task lock; cleanup deferred')
        _verify(state['protected'], full=full)

    try:
        with _lock(state_path):
            guard(full=True)
            completed = _completed(log)
            for candidate in state['candidates']:
                path = candidate['path']
                if (path, candidate.get('sha256'), candidate.get('mtime_ns')) in completed:
                    continue
                guard()
                try:
                    safe = _inside(path, scope)
                    if safe in metadata or any(safe == Path(p) or Path(p) in safe.parents for p in state['protected']):
                        raise ValueError('Protected candidate')
                    actual = _snapshot(safe)
                    if actual != {key: candidate[key] for key in actual}:
                        raise ValueError('Candidate changed since plan')
                    guard()
                    _log(log, {'event': 'attempt', **candidate})
                    receipts = (recycler or (lambda paths: _native_recycle(paths, scope)))([str(safe)])
                    receipt = next((item for item in receipts if item.get('path') == str(safe)), {})
                    if receipt.get('status') != 'recycled' or safe.exists():
                        raise ValueError(receipt.get('reason', 'No confirmed recycle success receipt'))
                    _log(log, {'event': 'recycled', **candidate})
                    result['count'] += 1
                    result['moved_bytes'] += candidate['bytes']
                except (ValueError, OSError, subprocess.SubprocessError, TypeError) as error:
                    skipped = {'path': path, 'reason': str(error)}
                    result['skipped'].append(skipped)
                    _log(log, {'event': 'skipped', **skipped})
            guard(full=True)
    except (ValueError, OSError) as error:
        result['status'] = 'blocked'
        result['reason'] = str(error)
        _log(log, {'event': 'blocked', 'reason': str(error)})
    result['completed'] = result['status'] == 'ok' and not result['skipped']
    return result
