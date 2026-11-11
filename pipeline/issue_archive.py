"""Copy a historical issue into a self-contained, hash-verified date archive.

Originals in review/immutable-originals are evidence only; their historical
machine paths are deliberately preserved. Operational inputs live elsewhere.
"""
import copy
import html
import os
import re
import shutil
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlsplit

from .core import ROOT, read_json, sha256, write_json
from .storage import classify_file, valid_day


_ATTR = re.compile(r'''(\b(?:src|href|poster)\s*=\s*)(?:(["'])(.*?)\2|([^\s"'=<>`]+))''', re.I | re.S)
_CSS = re.compile(r'''(url\(\s*)(["']?)([^)'"\s]+)\2(\s*\))''', re.I)
_SRCSET = re.compile(r'''(\bsrcset\s*=\s*)(["'])(.*?)\2''', re.I | re.S)
_REMOTE = {'http', 'https', 'data', 'mailto', 'tel', 'javascript', 'blob'}


def _local_ref(value):
    value = html.unescape(value).strip()
    if not value or value.startswith(('#', '//')):
        return None
    parts = urlsplit(value)
    # urlsplit treats C:/... as a URL scheme.
    if parts.scheme.lower() in _REMOTE:
        return None
    if parts.scheme and parts.scheme != 'file' and not re.match(r'^[A-Za-z]:[\\/]', value):
        raise ValueError(f'Unsupported local reference: {value}')
    if re.match(r'^[A-Za-z]:[\\/]', value):
        return value, ''
    path = unquote(parts.path)
    if parts.scheme == 'file':
        if parts.netloc:
            path = '//' + parts.netloc + path
        if os.name == 'nt' and re.match(r'^/[A-Za-z]:', path):
            path = path[1:]
    suffix = ('?' + parts.query if parts.query else '') + ('#' + parts.fragment if parts.fragment else '')
    return path, suffix


def _resolve(value, base):
    parsed = _local_ref(str(value))
    if parsed is None:
        raise ValueError(f'Expected a local file: {value}')
    name, _ = parsed
    path = Path(name)
    candidates = [path] if path.is_absolute() else [base/path, ROOT/path]
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    raise FileNotFoundError(f'{value} (relative to {base})')


def _relative(path, parent):
    return Path(os.path.relpath(path, parent)).as_posix()


def _rewrite_html(document, rewrite):
    def attribute(match):
        quote = match[2] or '"'
        return match[1] + quote + html.escape(rewrite(html.unescape(match[3] if match[2] else match[4])), quote=True) + quote
    document = _ATTR.sub(attribute, document)
    def srcset(match):
        entries = []
        # Data URIs contain commas; leave an entirely embedded srcset alone.
        if match[3].lstrip().lower().startswith('data:'):
            return match[0]
        for entry in match[3].split(','):
            fields = entry.strip().split()
            if fields:
                entries.append(' '.join([rewrite(html.unescape(fields[0])), *fields[1:]]))
        return match[1] + match[2] + html.escape(', '.join(entries), quote=True) + match[2]
    document = _SRCSET.sub(srcset, document)
    return _CSS.sub(lambda m: m[1] + m[2] + rewrite(m[3]) + m[2] + m[4], document)


def export_issue(pointer: dict, target: Path, _asset_namespace=None):
    """Export without changing a source file or replacing an existing archive.

    Relative pointer paths are resolved against the current directory. Missing
    edition/player/report keys default to edition.json/watch.html/daily.html in
    run_dir. Failure removes only this operation's temporary staging directory.
    """
    day = valid_day(pointer.get('date'))
    target = Path(target).resolve()
    if target.exists() and (not target.is_dir() or any(target.iterdir())):
        raise FileExistsError(target)
    run = Path(pointer.get('run_dir') or Path(pointer['video']).parent).resolve()
    inputs = {key: _resolve(pointer.get(key, run/default), Path.cwd()) for key, default in
              [('video', 'news.mp4'), ('player', 'watch.html'), ('report', 'daily.html'), ('edition', 'edition.json')]}
    edition = read_json(inputs['edition'])
    if edition.get('date') != day:
        raise ValueError('Pointer and edition dates disagree')
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix='.' + target.name + '-archive-', dir=target.parent))
    try:
        result = _export(pointer, day, run, inputs, edition, staging, _asset_namespace)
        verify_issue(staging)
        if target.exists():
            target.rmdir()  # Only an empty directory can be removed.
        staging.rename(target)
        return result
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def _export(pointer, day, run, inputs, edition, root, asset_namespace=None):
    if asset_namespace is not None and not re.fullmatch(r'[A-Za-z0-9_-]+', asset_namespace):
        raise ValueError('Invalid finalization asset namespace')
    for directory in ('editorial', 'media/images', 'media/videos', 'media/evidence',
                      'audio/source', 'audio/cues', 'production/runs',
                      'deliverables/current', 'review/immutable-originals', 'tasks'):
        (root/directory).mkdir(parents=True, exist_ok=True)
    delivered = root/'deliverables/current'
    originals = root/'review/immutable-originals'
    mapped = {}
    source_hashes = {}
    pages = []

    def put(source, destination, operational=True):
        source = Path(source).resolve()
        if not source.is_file():
            raise FileNotFoundError(source)
        digest = sha256(source)
        if asset_namespace and destination.relative_to(root).parts[0] in {'media', 'audio'}:
            destination = destination.parent/asset_namespace/destination.name
        if destination.exists() and sha256(destination) != digest:
            destination = destination.with_name(destination.stem + '-' + digest[:12] + destination.suffix)
        if not destination.exists():
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
        if sha256(destination) != digest:
            raise ValueError(f'Copy hash changed: {source}')
        source_hashes[source] = digest
        if operational:
            mapped[source] = destination
        return destination

    put(inputs['video'], delivered/'news.mp4')
    # Reserve page destinations before following cyclic navigation links.
    for key, name in [('player', 'watch.html'), ('report', 'daily.html')]:
        mapped[inputs[key]] = delivered/name
        pages.append((inputs[key], delivered/name))
    # Mixed editions' reports can still point to the earlier run's player.
    # Navigation in the exported report must open the selected final master.
    if (run/'watch.html').is_file():
        mapped[(run/'watch.html').resolve()] = delivered/'watch.html'
    put(inputs['edition'], originals/'edition.json', False)
    write_json(originals/'source-pointer.json', pointer)
    (originals/'README.txt').write_text(
        'IMMUTABLE HISTORICAL PROVENANCE ONLY. These original documents may contain\n'
        'old absolute machine paths. They are not portable operational inputs.\n'
        'Use editorial/edition.json and ISSUE_MANIFEST.json for this archive.\n', encoding='utf8')

    def dependency(source):
        source = source.resolve()
        if source in mapped:
            return mapped[source]
        group = classify_file(source)
        destination = root/'media'/group/source.name
        if source.suffix.lower() in {'.html', '.htm', '.css'}:
            destination = put(source, delivered/source.name if source.suffix.lower() != '.css' else destination)
            pages.append((source, destination))
            return destination
        return put(source, destination)

    def rewrite_paths(value, base, output_parent, evidence=False):
        if isinstance(value, list):
            return [rewrite_paths(item, base, output_parent, evidence) for item in value]
        if not isinstance(value, dict):
            return value
        result = {}
        for key, item in value.items():
            if key == 'path' and isinstance(item, str) and item:
                source = _resolve(item, base)
                destination = put(source, root/'media/evidence'/source.name) if evidence else dependency(source)
                result[key] = _relative(destination, output_parent)
            else:
                result[key] = rewrite_paths(item, base, output_parent, evidence or key == 'date_evidence')
        return result

    portable = rewrite_paths(copy.deepcopy(edition), inputs['edition'].parent, root/'editorial')
    # Final PCM cue files are independent of the original speech-source manifest.
    for source in sorted(run.glob('cue-*.wav')):
        if re.fullmatch(r'cue-\d+\.wav', source.name):
            put(source, root/'audio/cues'/source.name)
    narration = run/'narration.wav'
    if narration.is_file():
        put(narration, root/'audio/combined-narration.wav')
    audio_source = edition.get('audio_manifest')
    audio_manifest = _resolve(audio_source, inputs['edition'].parent) if audio_source else run/'audio-manifest.json'
    if audio_manifest.is_file():
        put(audio_manifest, originals/'audio-manifest.json', False)
        audio = read_json(audio_manifest)
        for entry in audio.values():
            source = _resolve(entry['path'], inputs['edition'].parent)
            destination = mapped.get(source) or put(source, root/'audio/source'/source.name)
            entry['path'] = _relative(destination, root/'editorial')
        write_json(root/'editorial/audio-manifest.json', audio)
        portable['audio_manifest'] = 'audio-manifest.json'
    write_json(root/'editorial/edition.json', portable)

    # Preserve render/source manifests byte-for-byte, separately from the ledger.
    for key in ('manifest', 'source_render_manifest', 'delivery_manifest'):
        if pointer.get(key):
            put(_resolve(pointer[key], Path.cwd()), originals/(key + '.json'), False)
    for filename in ('manifest.json', 'delivery-manifest.json'):
        if (run/filename).is_file():
            put(run/filename, originals/filename, False)
    for filename in ('subtitles.srt', 'subtitles.vtt', 'chapters.json', 'chapters.vtt',
                     'chapters.ffmetadata', 'timeline.json', 'bgm-receipt.json', 'outro-receipt.json', 'CREDITS.txt'):
        explicit = pointer.get(filename)
        if filename in {'chapters.json', 'timeline.json'}:
            explicit = explicit or pointer.get(filename.removesuffix('.json'))
        candidates = [Path(explicit)] if explicit else [inputs['video'].parent/filename, run/filename]
        source = next((path for path in candidates if path.is_file()), None)
        if explicit and source is None:
            raise FileNotFoundError(explicit)
        if source:
            put(source, delivered/filename)

    if asset_namespace and (delivered/'timeline.json').is_file():
        def timeline_paths(value):
            if isinstance(value, list):
                return [timeline_paths(item) for item in value]
            if not isinstance(value, dict):
                return value
            result = {}
            for key, item in value.items():
                if key in {'path', 'audio', 'source_file', 'raw_file', 'output_file_before_loudness', 'frame'} and isinstance(item, str):
                    source = (run/item).resolve()
                    result[key] = _relative(mapped[source], delivered) if source in mapped else item
                else:
                    result[key] = timeline_paths(item)
            return result
        write_json(delivered/'timeline.json', timeline_paths(read_json(delivered/'timeline.json')))

    done = set()
    operational_resources = []
    while pages:
        source, destination = pages.pop(0)
        if source in done:
            continue
        done.add(source)
        digest = sha256(source)

        def rewrite(value):
            parsed = _local_ref(value)
            if parsed is None:
                return value
            path, suffix = parsed
            dependency_source = _resolve(path, source.parent)
            return _relative(dependency(dependency_source), destination.parent) + suffix

        document = _rewrite_html(source.read_text(encoding='utf-8-sig'), rewrite)
        destination.write_text(document, encoding='utf8')
        operational_resources.append(destination.relative_to(root).as_posix())
        source_hashes[source] = digest
    for source, digest in source_hashes.items():
        if sha256(source) != digest:
            raise ValueError(f'Source changed during export: {source}')
    status = dict(date=day, status='archived', archive_status='verified',
                  publication_status=pointer.get('publication_status', 'not_published'),
                  tasks=[dict(id='ARCH-03', status='complete')], manifest='../ISSUE_MANIFEST.json')
    write_json(root/'tasks/status.json', status)
    files = {path.relative_to(root).as_posix(): dict(sha256=sha256(path), bytes=path.stat().st_size)
             for path in sorted(root.rglob('*')) if path.is_file()}
    manifest = dict(version=1, date=day, status='archived', files=files,
                    video='deliverables/current/news.mp4', edition='editorial/edition.json',
                    operational_resources=sorted(set(operational_resources)),
                    immutable_historical_provenance='review/immutable-originals',
                    provenance_policy='Historical originals may contain absolute paths; never use as operational inputs.')
    write_json(root/'ISSUE_MANIFEST.json', manifest)
    return manifest


def verify_issue(target: Path, finalization_ledger=None):
    """Verify a sealed archive, or one explicitly selected current finalization.

    Finalization ledgers cover only published artifacts; ongoing authoring files
    intentionally remain outside that ledger and may continue to change.
    """
    root = Path(target).resolve()

    def contained(name, base=root):
        path = Path(name)
        if path.is_absolute() or re.match(r'^[A-Za-z]:', str(name)):
            raise ValueError(f'Absolute operational path: {name}')
        result = (base/path).resolve()
        if not result.is_relative_to(root):
            raise ValueError(f'Archive path escapes root: {name}')
        if not result.is_file():
            raise FileNotFoundError(result)
        return result

    manifest = read_json(contained(finalization_ledger or 'ISSUE_MANIFEST.json'))
    valid_day(manifest['date'])
    for name, expected in manifest['files'].items():
        path = contained(name)
        if path.stat().st_size != expected['bytes'] or sha256(path) != expected['sha256']:
            raise ValueError(f'Archive hash mismatch: {name}')
    if finalization_ledger is None:
        actual = {p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file() and p != root/'ISSUE_MANIFEST.json'}
        if actual != set(manifest['files']):
            raise ValueError('Archive files differ from hash ledger')
    # Raw source/date-proof HTML is immutable evidence, not a page we serve.
    # Only documents rewritten by this exporter have portable link contracts.
    resources = manifest.get('operational_resources', [name for name in manifest['files'] if name.startswith('deliverables/current/')])
    for name in resources:
        if name not in manifest['files']:
            raise ValueError(f'Operational resource missing from ledger: {name}')
        path = contained(name)
        if path.suffix.lower() in {'.html', '.htm', '.css'}:
            def check(value):
                parsed = _local_ref(value)
                if parsed is not None:
                    contained(parsed[0], path.parent)
                return value
            _rewrite_html(path.read_text('utf8'), check)

    def check_paths(value, base):
        if isinstance(value, dict):
            for key, item in value.items():
                if key in {'path', 'audio_manifest'} and isinstance(item, str) and item:
                    contained(item, base)
                else:
                    check_paths(item, base)
        elif isinstance(value, list):
            for item in value:
                check_paths(item, base)
    contained(manifest['video'])
    edition_path = contained(manifest['edition'])
    edition = read_json(edition_path)
    if edition.get('date') != manifest['date']:
        raise ValueError('Archive edition date mismatch')
    check_paths(edition, edition_path.parent)
    if edition.get('audio_manifest'):
        check_paths(read_json(contained(edition['audio_manifest'], edition_path.parent)), edition_path.parent)
    return manifest


def _guard_archive_path(path):
    """Reject directory redirection before moving anything inside an issue."""
    path = Path(path).absolute()
    for item in (path, *path.parents):
        if item.is_symlink() or (item.exists() and getattr(item.lstat(), 'st_file_attributes', 0) & 0x400):
            raise ValueError(f'Archive path contains a symlink/junction/reparse point: {item}')
    return path.resolve()


def publish_current(pointer: dict, target_issue: Path):
    """Finalize reviewed output into a populated issue without replacing inputs.

    Existing media/audio collisions fail before installation. Only current is
    replaced; its previous directory is retained in deliverables/history-*. The
    returned ledger can be checked with verify_issue(issue, result['ledger']).
    Sealed historical archives must continue to use their immutable root ledger.
    """
    day = valid_day(pointer.get('date'))
    root = _guard_archive_path(target_issue)
    if (root/'ISSUE_MANIFEST.json').exists():
        raise FileExistsError('A sealed historical archive cannot receive current finalizations')
    authoring = root/'editorial/edition.json'
    if authoring.is_file() and read_json(authoring).get('date') != day:
        raise ValueError('Authoring edition and finalization dates disagree')
    root.parent.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '-' + uuid.uuid4().hex[:8]
    current = root/'deliverables/current'
    candidate = root/'deliverables'/('.current-' + run_id)
    # Keep backups at current's depth so their relative media links still work.
    history = root/'deliverables'/('history-' + run_id)
    receipt = root/'review/finalizations'/run_id
    for path in (current, candidate, history, receipt):
        resolved = _guard_archive_path(path)
        if not resolved.is_relative_to(root):
            raise ValueError(f'Finalization path escapes issue: {path}')
    if current.exists() and not current.is_dir():
        raise FileExistsError(current)
    with tempfile.TemporaryDirectory(prefix='.finalize-', dir=root.parent) as temp:
        snapshot = Path(temp)/'snapshot'
        exported = export_issue(pointer, snapshot, _asset_namespace=run_id)
        installation = []
        for source in sorted(snapshot.rglob('*')):
            if not source.is_file():
                continue
            relative = source.relative_to(snapshot)
            if relative.parts[0] in {'media', 'audio'}:
                destination = root/relative
            elif relative.as_posix().startswith('review/immutable-originals/'):
                destination = receipt/'immutable-originals'/source.name
            else:
                continue
            _guard_archive_path(destination)
            if destination.exists() and (not destination.is_file() or sha256(destination) != sha256(source)):
                raise FileExistsError(f'Finalization would overwrite different content: {destination}')
            installation.append((source, destination))

        # A portable editorial copy belongs to the finalized output, leaving the
        # editor's draft, candidates, proof files, and task records untouched.
        def rebase(value):
            if isinstance(value, list):
                return [rebase(item) for item in value]
            if not isinstance(value, dict):
                return value
            result = {}
            for key, item in value.items():
                if key == 'path' and isinstance(item, str) and item:
                    source = (snapshot/'editorial'/item).resolve()
                    result[key] = _relative(root/source.relative_to(snapshot), current)
                else:
                    result[key] = rebase(item)
            return result

        candidate.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copytree(snapshot/'deliverables/current', candidate)
            edition = rebase(read_json(snapshot/'editorial/edition.json'))
            write_json(candidate/'edition.json', edition)
            if edition.get('audio_manifest'):
                write_json(candidate/'audio-manifest.json', rebase(read_json(snapshot/'editorial/audio-manifest.json')))
            for source, destination in installation:
                if not destination.exists():
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    # Exclusive creation also guards against races after preflight.
                    with source.open('rb') as incoming, destination.open('xb') as output:
                        shutil.copyfileobj(incoming, output)
            files = {destination.relative_to(root).as_posix(): dict(sha256=sha256(destination), bytes=destination.stat().st_size)
                     for _, destination in installation}
            for source in candidate.rglob('*'):
                if source.is_file():
                    name = (current/source.relative_to(candidate)).relative_to(root).as_posix()
                    files[name] = dict(sha256=sha256(source), bytes=source.stat().st_size)
            manifest = dict(version=1, date=day, status='finalized', files=files,
                            video='deliverables/current/news.mp4', edition='deliverables/current/edition.json',
                            operational_resources=exported['operational_resources'],
                            publication_status=pointer.get('publication_status', 'not_published'),
                            immutable_historical_provenance=receipt.relative_to(root).as_posix()+'/immutable-originals')
            # Guard again immediately before both directory moves.
            for path in (current, candidate, history):
                _guard_archive_path(path)
            if current.exists():
                history.parent.mkdir(parents=True, exist_ok=True)
                current.rename(history)
            try:
                candidate.rename(current)
            except BaseException:
                if history.exists() and not current.exists():
                    history.rename(current)
                raise
            ledger = receipt/'ISSUE_MANIFEST.json'
            ledger_name = ledger.relative_to(root).as_posix()
            try:
                write_json(ledger, manifest)
                verify_issue(root, ledger_name)
            except BaseException:
                _guard_archive_path(current)
                current.rename(receipt/'failed-current')
                if history.exists():
                    _guard_archive_path(history)
                    history.rename(current)
                raise
            return dict(manifest, ledger=ledger_name,
                        previous_current=history.relative_to(root).as_posix() if history.exists() else None)
        finally:
            if candidate.exists():
                _guard_archive_path(candidate)
                shutil.rmtree(candidate)
