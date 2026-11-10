"""Fail-closed standard-library updater for verified ZIP archives or loose files."""
import contextlib
import hashlib
import io
import json
import os
import re
import shutil
import stat
import tempfile
import urllib.parse
import urllib.request
import uuid
import zipfile
import zlib
from pathlib import Path, PurePosixPath


class UpdateError(RuntimeError):
    pass


MANIFEST = 'architecture/release.json'
ALLOWED_DIRS = {'pipeline', 'scripts', 'tests', 'config', 'assets', 'skills', 'docs', 'architecture'}
RESERVED = re.compile(r'^(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\.|$)', re.I)
MAX_ARCHIVE_BYTES = 20 * 1024 * 1024
MAX_ARCHIVE_UNCOMPRESSED = 50 * 1024 * 1024


def _hash(content):
    return hashlib.sha256(content).hexdigest()


def _safe_name(name):
    if (not isinstance(name, str) or not name or '\\' in name or ':' in name
            or re.search(r'[\x00-\x1f<>"?*|]', name)):
        raise UpdateError(f'Unsafe managed path: {name!r}')
    parts = PurePosixPath(name).parts
    if (name.startswith('/') or '/'.join(parts) != name or
            any(p in {'.', '..'} or p.endswith(('.', ' ')) or RESERVED.match(p) for p in parts)):
        raise UpdateError(f'Unsafe managed path: {name!r}')
    lower = name.lower()
    if (any(p.lower() in {'data', 'outputs', 'runtime', '.venv', '.tools', '__pycache__', '.git'} for p in parts)
            or '.local.' in lower or lower.endswith('.local') or lower.endswith(('.pyc', '.pyo'))
            or (parts[0].lower() == 'docs' and re.search(r'20\d{2}[-_]?\d{2}[-_]?\d{2}', name))):
        raise UpdateError(f'User/local data cannot be managed: {name}')
    if len(parts) == 1:
        if not (lower in {'.gitignore', 'readme.md', 'quick_start.md', 'architecture.md', 'requirements.txt'}
                or Path(name).suffix.lower() in {'.bat', '.ps1', '.html', '.css', '.js'}):
            raise UpdateError(f'Unknown managed root file: {name}')
    elif parts[0] not in ALLOWED_DIRS:
        raise UpdateError(f'Unknown managed directory: {name}')
    if parts[0] == 'architecture' and name != 'architecture/managed-files.json':
        raise UpdateError(f'Architecture manifest is managed separately: {name}')
    if parts[0] == 'skills' and (len(parts) < 3 or parts[1] != 'nau-cea-daily-video'):
        raise UpdateError(f'Unknown managed skill: {name}')
    return name


def _no_links(path):
    """Reject Windows junctions and ordinary symlinks, including ancestors."""
    path = Path(path).absolute()
    for item in [*reversed(path.parents), path]:
        try:
            info = item.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
            raise UpdateError(f'Symlink or junction is not allowed: {item}')
        if item != path and not stat.S_ISDIR(info.st_mode):
            raise UpdateError(f'Non-directory ancestor: {item}')


def _target(root, name):
    path = root / _safe_name(name)
    _no_links(path)
    if path.exists() and not path.is_file():
        raise UpdateError(f'Managed path is not a regular file: {path}')
    return path


def _json(path):
    try:
        _no_links(path)
        return json.loads(Path(path).read_text(encoding='utf-8-sig'))
    except (OSError, ValueError) as error:
        raise UpdateError(f'Cannot read JSON {path}: {error}') from error


def _version(value):
    if not isinstance(value, str) or not re.fullmatch(r'(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)', value):
        raise UpdateError(f'Expected release version MAJOR.MINOR.PATCH, got {value!r}')
    return tuple(map(int, value.split('.')))


def _manifest(value):
    if not isinstance(value, dict):
        raise UpdateError('Release manifest must be an object')
    for key in ('architecture_version', 'skill_version'):
        _version(value.get(key))
    files = value.get('files')
    if not isinstance(files, dict) or not files:
        raise UpdateError('Release manifest files must be a non-empty path/hash object')
    folded = set()
    for name, digest in files.items():
        _safe_name(name)
        if name.casefold() in folded:
            raise UpdateError(f'Duplicate case-insensitive path: {name}')
        folded.add(name.casefold())
        if not isinstance(digest, str) or not re.fullmatch('[0-9a-f]{64}', digest):
            raise UpdateError(f'Invalid SHA256 hash: {name}')
    if any(str(parent) in folded for name in folded for parent in PurePosixPath(name).parents):
        raise UpdateError('Manifest contains a file/directory path collision')
    if 'archive' in value:
        archive = value['archive']
        if (not isinstance(archive, dict) or not isinstance(archive.get('sha256'), str)
                or not re.fullmatch('[0-9a-f]{64}', archive['sha256'])):
            raise UpdateError('Archive needs a URL and SHA256 hash')
        _archive_url('https://updates.invalid/release.json', archive.get('url'))
        if 'bytes' in archive and (type(archive['bytes']) is not int
                                  or not 0 < archive['bytes'] <= MAX_ARCHIVE_BYTES):
            raise UpdateError('Invalid archive byte size')
    return value


def _source_url(url):
    if not isinstance(url, str) or not url or re.search(r'[\x00-\x20\\]', url):
        raise UpdateError('Invalid update source URL')
    try:
        parsed = urllib.parse.urlsplit(url)
        parsed.port
    except ValueError as error:
        raise UpdateError(f'Invalid update source URL: {error}') from error
    if parsed.scheme == 'file':
        if parsed.netloc not in ('', 'localhost') or parsed.query or parsed.fragment:
            raise UpdateError('Unsupported file source URL')
        path = Path(urllib.request.url2pathname(parsed.path))
        if not path.is_absolute():
            raise UpdateError('File source URI must be absolute')
    elif (parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password
            or parsed.fragment or parsed.query):
        raise UpdateError('Update source must be a file URI or HTTPS URL without credentials/query/fragment')
    return parsed


def _archive_url(source, url):
    if not isinstance(url, str) or not url:
        raise UpdateError('Archive URL must be a non-empty string')
    if ':' not in url:
        parts = PurePosixPath(url).parts
        if (not parts or url.startswith('/') or '/'.join(parts) != url
                or any(p in {'.', '..'} for p in parts) or re.search(r'[\x00-\x20\\?#%]', url)):
            raise UpdateError('Relative archive URL must be a canonical sibling path')
        url = urllib.parse.urljoin(source, url)
    _source_url(url)
    return url


def _read_source(url, *, max_bytes=None):
    parsed = _source_url(url)
    if parsed.scheme == 'file':
        path = Path(urllib.request.url2pathname(parsed.path))
        _no_links(path)
        if not path.is_file():
            raise UpdateError(f'Cannot read update source file: {path}')
        with path.open('rb') as handle:
            content = handle.read(max_bytes + 1) if max_bytes is not None else handle.read()
        if max_bytes is not None and len(content) > max_bytes:
            raise UpdateError('Update source exceeds byte limit')
        return content
    try:
        request = urllib.request.Request(url, headers={'Cache-Control': 'no-cache', 'Pragma': 'no-cache'})
        with urllib.request.urlopen(request, timeout=30) as response:
            if _source_url(response.url).scheme != 'https':
                raise UpdateError('HTTPS source redirected to an insecure scheme')
            content = response.read(max_bytes + 1) if max_bytes is not None else response.read()
            if max_bytes is not None and len(content) > max_bytes:
                raise UpdateError('Update source exceeds byte limit')
            return content
    except (OSError, ValueError) as error:
        raise UpdateError(f'Cannot read update source {url}: {error}') from error


def _source(root):
    local = root / 'config/updates.local.json'
    config = local if local.exists() else root / 'config/updates.json'
    if not config.exists():
        raise UpdateError('Update source is not configured: config/updates[.local].json')
    settings = _json(config)
    source = settings.get('source') if isinstance(settings, dict) else None
    if not isinstance(source, str) or not source.strip():
        raise UpdateError('Update source is not configured; set source to a file URI or HTTPS release.json URL')
    # Bundles may ship a real frozen baseline release inside their own tree.
    # This is a local channel, never evidence of checking a shared upstream.
    if ':' not in source:
        parts = PurePosixPath(source).parts
        if (not parts or source.startswith('/') or '/'.join(parts) != source
                or any(p in {'.', '..'} for p in parts) or '\\' in source
                or re.search(r'[\x00-\x1f<>"?*|]', source)):
            raise UpdateError('Relative update source must stay inside the project')
        path = root / source
        _no_links(path)
        source = path.as_uri()
    return source


def _check_render_locks(root):
    data = os.environ.get('NJAU_CEA_DATA_ROOT', '').strip()
    if not data and (root / 'config/storage.local.json').exists():
        data = _json(root / 'config/storage.local.json').get('data_root', '')
    data_path = Path(data) if data else root / 'data'
    if not data_path.is_absolute():
        data_path = root / data_path
    for lock in (root / 'outputs/daily/.render.lock', root / 'data/.render.lock', data_path / '.render.lock'):
        if lock.exists() or lock.is_symlink():
            raise UpdateError(f'Active render lock blocks update: {lock}')


@contextlib.contextmanager
def _lock(root):
    runtime = root / 'runtime'
    _no_links(runtime)
    runtime.mkdir(parents=True, exist_ok=True)
    lock = runtime / 'update.lock'
    _no_links(lock)
    token = f'{os.getpid()}:{uuid.uuid4().hex}'
    try:
        with lock.open('x', encoding='utf-8') as handle:
            handle.write(token)
    except FileExistsError as error:
        raise UpdateError(f'Update lock already exists: {lock}; do not remove a live lock') from error
    try:
        yield
    finally:
        if lock.is_file() and not lock.is_symlink() and lock.read_text(encoding='utf-8') == token:
            lock.unlink()


def _check_local(root, installed, incoming):
    for name, digest in installed['files'].items():
        path = _target(root, name)
        if not path.is_file() or _hash(path.read_bytes()) != digest:
            raise UpdateError(f'Local modified or missing managed file conflicts with update: {name}')
    for name in incoming['files']:
        path = _target(root, name)
        if name not in installed['files'] and path.exists():
            raise UpdateError(f'Unmanaged local file conflicts with update: {name}')


@contextlib.contextmanager
def production_guard(root, receipt):
    """Hold the updater's exclusion lock throughout production.

    Acquire before importing render code or creating the render lock, and keep
    it until the render lock is released. A previous freshness receipt may be
    stale after waiting between the update check and entering production.
    """
    root = Path(root).absolute()
    with _lock(root):
        if (not isinstance(receipt, dict) or receipt.get('status') != 'current'
                or receipt.get('rerun_required')):
            raise UpdateError('Production needs a current update receipt; restart and check updates again')
        installed = _manifest(_json(root / MANIFEST))
        for key in ('architecture_version', 'skill_version'):
            if receipt.get(key) != installed[key]:
                raise UpdateError(f'Stale production receipt for {key}; restart and check updates again')
        _check_local(root, installed, installed)
        _check_render_locks(root)
        yield


def _atomic_write(path, content):
    _no_links(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        temporary.write_bytes(content)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _stage_archive(source, incoming, stage):
    archive = incoming['archive']
    try:
        content = _read_source(_archive_url(source, archive['url']), max_bytes=MAX_ARCHIVE_BYTES)
    except OSError as error:
        raise UpdateError(f'Cannot read update archive: {error}') from error
    if len(content) > MAX_ARCHIVE_BYTES or ('bytes' in archive and len(content) != archive['bytes']):
        raise UpdateError('Archive byte size mismatch or limit exceeded')
    if _hash(content) != archive['sha256']:
        raise UpdateError('Archive SHA256 hash mismatch')
    files = incoming['files']
    directories = {str(parent) for name in files for parent in PurePosixPath(name).parents
                   if str(parent) != '.'}
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as bundle:
            seen, members, total = set(), {}, 0
            for entry in bundle.infolist():
                name = entry.orig_filename
                directory = name.endswith('/')
                name = name[:-1] if directory else name
                if (entry.filename != entry.orig_filename or name.casefold() in seen
                        or (directory and name not in directories)
                        or (not directory and _safe_name(name) not in files)):
                    raise UpdateError(f'Unknown, unsafe or duplicate archive member: {entry.orig_filename!r}')
                seen.add(name.casefold())
                kind = stat.S_IFMT(entry.external_attr >> 16)
                if (kind not in (0, stat.S_IFDIR if directory else stat.S_IFREG)
                        or entry.external_attr & 0x400 or entry.flag_bits & 1
                        or (not directory and entry.external_attr & 0x10)
                        or (directory and entry.file_size)):
                    raise UpdateError(f'Non-regular archive member: {name}')
                total += entry.file_size
                if total > MAX_ARCHIVE_UNCOMPRESSED:
                    raise UpdateError('Archive uncompressed byte limit exceeded')
                if not directory:
                    members[name] = entry
            if members.keys() != files.keys():
                raise UpdateError('Archive does not contain exactly the listed release files')
            for name, entry in members.items():
                with bundle.open(entry) as handle:
                    data = handle.read(entry.file_size + 1)
                if len(data) != entry.file_size or _hash(data) != files[name]:
                    raise UpdateError(f'Archive file SHA256 hash mismatch: {name}')
                target = stage / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
    except (OSError, ValueError, RuntimeError, zipfile.BadZipFile, zlib.error) as error:
        raise UpdateError(f'Cannot verify update archive: {error}') from error


def ensure_current(root=None, *, apply=True, offline=False):
    """Read source on each call; restart caller if rerun_required is true.

    Offline is explicit inspection and never reports current. A current result
    verifies the installed content too, including when versions are unchanged.
    """
    root = (Path(root) if root is not None else Path(__file__).resolve().parents[1]).absolute()
    _no_links(root / MANIFEST)
    installed = _manifest(_json(root / MANIFEST))
    versions = {key: installed[key] for key in ('architecture_version', 'skill_version')}
    if offline:
        return dict(status='offline', rerun_required=False, **versions)
    with _lock(root):
        _check_render_locks(root)
        source = _source(root)
        try:
            incoming = _manifest(json.loads(_read_source(source).decode('utf-8-sig')))
        except (OSError, ValueError) as error:
            raise UpdateError(f'Cannot read release source: {error}') from error
        _check_local(root, installed, incoming)
        for key in versions:
            if _version(incoming[key]) < _version(installed[key]):
                raise UpdateError(f'Release rollback rejected: {key} {installed[key]} -> {incoming[key]}')
        newer = any(_version(incoming[key]) > _version(installed[key]) for key in versions)
        if not newer and incoming['files'] != installed['files']:
            raise UpdateError('Release files changed without a higher architecture or skill version')
        if not newer:
            return dict(status='current', source=source, rerun_required=False, **versions)
        if not apply:
            return dict(status='available', source=source, rerun_required=True,
                        **{key: incoming[key] for key in versions})
        with tempfile.TemporaryDirectory(prefix='update-stage-', dir=root / 'runtime') as temporary:
            stage = Path(temporary)
            if 'archive' in incoming:
                _stage_archive(source, incoming, stage)
            for name, digest in (() if 'archive' in incoming else incoming['files'].items()):
                url = urllib.parse.urljoin(source, urllib.parse.quote(name, safe='/'))
                try:
                    content = _read_source(url)
                except OSError as error:
                    raise UpdateError(f'Cannot read update source file {name}: {error}') from error
                if _hash(content) != digest:
                    raise UpdateError(f'SHA256 hash mismatch: {name}')
                target = stage / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)
            _check_local(root, installed, incoming)
            _check_render_locks(root)
            backup = root / 'runtime/update-backups' / uuid.uuid4().hex
            _no_links(backup)
            backup.mkdir(parents=True)
            touched = list(dict.fromkeys([*installed['files'], *incoming['files'], MANIFEST]))
            for name in touched:
                path = root / name
                if path.exists():
                    destination = backup / name
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(path, destination)
            (backup / 'transaction.json').write_text(json.dumps({'files': touched, 'source': source}), encoding='utf-8')
            try:
                for name in installed['files'].keys() - incoming['files'].keys():
                    _target(root, name).unlink()
                for name in incoming['files']:
                    _atomic_write(_target(root, name), (stage / name).read_bytes())
                _atomic_write(root / MANIFEST, (json.dumps(incoming, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))
            except Exception as error:
                failures = []
                for name in touched:
                    path, saved = root / name, backup / name
                    try:
                        _no_links(path)
                        if saved.exists():
                            path.parent.mkdir(parents=True, exist_ok=True)
                            shutil.copy2(saved, path)
                        else:
                            path.unlink(missing_ok=True)
                    except (OSError, UpdateError) as restore_error:
                        failures.append(f'{name}: {restore_error}')
                if failures:
                    raise UpdateError(f'Apply failed; rollback incomplete; backup {backup}: {failures}') from error
                raise UpdateError(f'Apply failed and rolled back; backup {backup}: {error}') from error
        return dict(status='updated', source=source, backup=str(backup), rerun_required=True,
                    **{key: incoming[key] for key in versions})


def publish_local_release(root, output):
    """Copy only verified explicit release files into an empty local directory."""
    root, output = Path(root).absolute(), Path(output).absolute()
    release = _manifest(_json(root / MANIFEST))
    _no_links(output)
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise UpdateError(f'Publish output must be an empty directory: {output}')
    contents = {}
    for name, digest in release['files'].items():
        path = _target(root, name)
        if not path.is_file():
            raise UpdateError(f'Missing managed release file: {name}')
        content = path.read_bytes()
        if _hash(content) != digest:
            raise UpdateError(f'Local release hash mismatch: {name}')
        contents[name] = content
    output.mkdir(parents=True, exist_ok=True)
    for name, content in contents.items():
        target = output / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    # This channel contains loose verified files, independently of the original ZIP source.
    local_release = {key: value for key, value in release.items() if key != 'archive'}
    (output / 'release.json').write_text(json.dumps(local_release, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return dict(status='published', source=(output / 'release.json').as_uri(), files=len(contents))
