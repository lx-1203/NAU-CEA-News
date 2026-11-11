"""Persistent no-repeat music rotation and bounded, disposable download sessions."""
import contextlib
import copy
import json
import os
import random
import re
import uuid
import subprocess
import math
from datetime import datetime
from pathlib import Path

from .core import TZ, sha256
from .storage import valid_day
from .updates import _no_links


def _save(path, value):
    path = Path(path)
    _no_links(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        with temporary.open('xb') as stream:
            stream.write((json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf8'))
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


@contextlib.contextmanager
def music_lock(directory):
    """OS releases the lock on process exit; never delete or steal a live lock."""
    directory = Path(directory)
    _no_links(directory)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / '.lock'
    _no_links(path)
    with path.open('a+b') as handle:
        handle.seek(0, 2)
        if not handle.tell():
            handle.write(b'0'); handle.flush()
        handle.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise RuntimeError('Another BGM operation is active; retry after it finishes') from error
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == 'nt':
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle, fcntl.LOCK_UN)


class Rotation:
    """Caller holds music_lock for the complete reserve/download/render/commit."""
    def __init__(self, directory, catalog, choose=None):
        self.directory = Path(directory)
        self.path = self.directory / 'history.json'
        self.catalog = catalog
        self.choose = choose or random.SystemRandom().choice
        self.tracks = {}
        for track in catalog['tracks']:
            if track.get('bgm_eligible') is False or track.get('id') == 'news-theme':
                continue
            self.tracks.setdefault(track['sha256'], track)

    def _read(self):
        _no_links(self.path)
        if not self.path.exists():
            state = dict(schema=1, cycle=1, used=[], last_sha256=None, assignments={}, pending=None)
            historical = []
            for track in self.tracks.values():
                for day in track.get('historical_usage', []):
                    if isinstance(day, str) and re.fullmatch(r'\d{4}-\d{2}-\d{2}', day):
                        valid_day(day)
                        historical.append((day, track))
            for day, track in sorted(historical, key=lambda item: item[0]):
                state['assignments'][day] = self._assignment(day, track, 1, historical=True)
                if track['sha256'] not in state['used']:
                    state['used'].append(track['sha256'])
                state['last_sha256'] = track['sha256']
            return state
        if self.path.stat().st_size > 16 * 1024 * 1024:
            raise ValueError('BGM history exceeds 16 MiB; preserve and inspect it')
        try:
            state = json.loads(self.path.read_text(encoding='utf-8-sig'))
            def require(condition):
                if not condition:raise ValueError('Invalid history structure')
            require(state['schema'] == 1 and type(state['cycle']) is int and state['cycle'] >= 1)
            require(isinstance(state['used'], list) and isinstance(state['assignments'], dict))
            require(len(state['used']) == len(set(state['used'])))
            require(all(re.fullmatch('[0-9a-f]{64}', digest) for digest in state['used']))
            for day, assignment in state['assignments'].items():
                valid_day(day)
                require(assignment['edition'] == day and assignment['cycle'] >= 1)
                require(re.fullmatch('[0-9a-f]{64}', assignment['track']['sha256']))
            pending = state['pending']
            if pending is not None:
                valid_day(pending['edition'])
                require(pending['cycle'] >= 1 and re.fullmatch('[0-9a-f]{64}', pending['track']['sha256']))
            require(state['last_sha256'] is None or re.fullmatch('[0-9a-f]{64}', state['last_sha256']))
        except (ValueError, KeyError, TypeError, AssertionError) as error:
            raise ValueError('BGM history is invalid; preserve it instead of resetting usage') from error
        return state

    def _assignment(self, day, track, cycle, **extra):
        return dict(edition=day, track=copy.deepcopy(track), cycle=cycle,
                    catalog_version=self.catalog['version'],
                    source=copy.deepcopy(self.catalog.get('download', {})), **extra)

    def reserve(self, day):
        valid_day(day)
        state = self._read()
        if day in state['assignments']:
            return copy.deepcopy(state['assignments'][day])
        if state['pending'] and state['pending']['edition'] == day:
            new_current=set(self.tracks)-set(state['used'])
            if not (state['pending']['cycle']>state['cycle'] and new_current):
                return copy.deepcopy(state['pending'])
        if not self.tracks:
            raise ValueError('No eligible daily BGM tracks in the catalog')
        used = set(state['used'])
        candidates = [track for digest, track in self.tracks.items() if digest not in used]
        if not candidates:
            # Only a successful commit advances a cycle; a failed export does not.
            cycle = state['cycle'] + 1
            candidates = list(self.tracks.values())
        else:
            cycle = state['cycle']
        different = [track for track in candidates if track['sha256'] != state['last_sha256']]
        selected = self.choose(different or candidates)
        state['pending'] = self._assignment(day, selected, cycle)
        _save(self.path, state)
        return copy.deepcopy(state['pending'])

    def commit(self, day, video_sha256):
        valid_day(day)
        if not isinstance(video_sha256, str) or not re.fullmatch('[0-9a-f]{64}', video_sha256):
            raise ValueError('A verified video SHA256 is required to commit BGM usage')
        state = self._read()
        if day in state['assignments']:
            assignment = state['assignments'][day]
        else:
            assignment = state['pending']
            if not assignment or assignment['edition'] != day:
                raise ValueError('No matching pending BGM selection')
            if assignment['cycle'] != state['cycle']:
                state['cycle'] = assignment['cycle']
                state['used'] = []
            digest = assignment['track']['sha256']
            if digest not in state['used']:
                state['used'].append(digest)
            state['last_sha256'] = digest
            state['assignments'][day] = assignment
        assignment.update(video_sha256=video_sha256, committed_at=datetime.now(TZ).isoformat())
        if state['pending'] and state['pending']['edition'] == day:
            state['pending'] = None
        _save(self.path, state)
        return copy.deepcopy(assignment)

    def status(self):
        state = self._read()
        state['eligible_tracks'] = len(self.tracks)
        state['remaining_in_cycle'] = len(set(self.tracks) - set(state['used']))
        return state


def clean_cache(directory):
    """Permanently discard ONLY re-downloadable files in this tool's own cache."""
    directory=Path(directory);_no_links(directory)
    directory.mkdir(parents=True,exist_ok=True)
    marker=directory/'OWNER.json';_no_links(marker)
    owner=dict(owner='njau-cea-bgm-download-cache',schema=1)
    if not marker.exists():
        if any(directory.iterdir()):raise ValueError('Refusing to adopt a nonempty unowned BGM cache')
        _save(marker,owner)
    if json.loads(marker.read_text(encoding='utf8'))!=owner:
        raise ValueError('BGM cache ownership marker is invalid')
    deleted=0;count=0
    for path in directory.iterdir():
        _no_links(path)
        if path==marker:continue
        if not path.is_file() or not re.fullmatch(r'[0-9a-f]{64}\.(mp3|ogg|wav|flac|m4a)(\.part)?',path.name):
            raise ValueError('Unexpected file in managed BGM cache; preserved: '+path.name)
        size=path.stat().st_size
        path.unlink()
        deleted+=size;count+=1
    return dict(status='clean',deleted_files=count,deleted_bytes=deleted,audio_bytes_after=0,
                policy='permanent_delete_of_owned_redownloadable_cache_only')


def settings(root):
    root=Path(root)
    path=root/'config/bgm.local.json'
    if not path.exists():path=root/'config/bgm.json'
    value=json.loads(path.read_text(encoding='utf-8-sig')) if path.exists() else {}
    if not isinstance(value,dict) or type(value.get('enabled',True)) is not bool:
        raise ValueError('Invalid BGM settings')
    return value


def music_directory(root):
    from .storage import data_root
    return data_root(root)/'music'


def _ffmpeg(args):
    import imageio_ffmpeg
    return subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-hide_banner','-v','error',*map(str,args)],
                          capture_output=True,check=True)


def true_peak(path):
    import imageio_ffmpeg
    result=subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-hide_banner','-nostats','-i',str(path),
        '-vn','-af','loudnorm=I=-18:TP=-3:LRA=7:print_format=json','-f','null','-'],capture_output=True,check=True)
    text=result.stderr.decode('utf8',errors='replace')
    stats=json.loads(text[text.rfind('{'):text.rfind('}')+1])
    peak=float(stats['input_tp'])
    if not math.isfinite(peak):raise ValueError('Mixed video audio is silent or cannot be measured')
    return peak


class BgmSession:
    """A production transaction: live check, one download, then zero audio cache."""
    def __init__(self,root,day):
        self.root=Path(root);self.day=valid_day(day)
        self.directory=music_directory(root);self.cache=self.directory/'cache'
        self.options=settings(root)
        self.receipt=None;self.cleanup_receipt=None;self._cleaned=False

    def __enter__(self):
        from .bgm_source import refresh_catalog,download_track
        self._lock=music_lock(self.directory)
        self._lock.__enter__()
        try:
            clean_cache(self.cache)
            self.catalog=refresh_catalog(self.options)
            _save(self.directory/'catalog.json',self.catalog)
            self.rotation=Rotation(self.directory,self.catalog)
            self.selection=self.rotation.reserve(self.day)
            source=self.catalog.get('download',{})
            current=self.rotation.tracks.get(self.selection['track']['sha256'])
            audio_source={key:copy.deepcopy(self.selection[key]) for key in ('track','source','catalog_version')}
            if 'track_base_url' in source and current is not None:
                audio_source=dict(track=copy.deepcopy(current),source=copy.deepcopy(source),
                                  catalog_version=self.catalog['version'])
                self.audio,self.download=download_track(
                    audio_source['track'],audio_source['source'],self.cache,
                    local_music_directory=self.root/'assets/audio/music')
            else:
                self.audio,self.download=download_track(self.selection['track'],self.selection['source'],self.cache)
            _ffmpeg(['-xerror','-i',self.audio,'-map','0:a:0','-vn','-f','null','-'])
            self.receipt=dict(schema=1,edition=self.day,status='prepared',
                selection=self.selection,audio_source=audio_source,download=self.download,source_audio_full_decode=True,
                local_audio_policy='temporary_download_deleted_at_session_exit')
            return self
        except BaseException:
            try:self._clean()
            finally:self._lock.__exit__(None,None,None)
            raise

    def _clean(self):
        self.cleanup_receipt=clean_cache(self.cache)
        _save(self.directory/'last-cleanup.json',self.cleanup_receipt)
        self._cleaned=True

    def seal_cache(self):
        """Delete transient audio before sealing artifact metadata and history."""
        if not self._cleaned:self._clean()
        return copy.deepcopy(self.cleanup_receipt)

    def __exit__(self,kind,value,traceback):
        try:
            if not self._cleaned:self._clean()
        finally:self._lock.__exit__(kind,value,traceback)
        return False

    def mix(self,source,target,timeline):
        import imageio_ffmpeg
        source=Path(source);target=Path(target)
        if source.resolve()==target.resolve() or target.exists():
            raise ValueError('BGM mixing requires a new output path')
        reader=imageio_ffmpeg.read_frames(str(source))
        try:duration=next(reader)['duration']
        finally:reader.close()
        if duration<=0:raise ValueError('Cannot mix BGM into empty video')
        intro=timeline.get('opening',{})
        opening=float(intro.get('duration_seconds',intro.get('end',0)))
        opening=max(opening,float(timeline.get('opening_offset_seconds',0)))
        muted=[(0,opening)] if opening else []
        muted.extend((float(item['start']),float(item['end'])) for item in timeline.get('interludes',[]))
        music_end = duration
        if timeline.get('outro'):
            tail = timeline['outro']
            music_end = float(tail['start'])
            muted.append((music_end, float(tail['end'])))
        for a,b in muted:
            if not 0<=a<b<=duration+.05:raise ValueError('Invalid BGM exclusion interval')
        expressions=[f'gte(t,{a:.6f})*lt(t,{b:.6f})' for a,b in muted]
        mask='not('+ '+'.join(expressions)+')' if expressions else '1'
        graph=(f'[0:a:0]asplit=2[voice][side];'
            f'[1:a:0]aformat=sample_rates=48000:channel_layouts=stereo,'
            f'loudnorm=I=-28:TP=-9:LRA=7,atrim=duration={duration:.6f},asetpts=PTS-STARTPTS,'
            f'afade=t=in:st={opening:.6f}:d=1.2,afade=t=out:st={max(opening,music_end-2):.6f}:d=2[bed];'
            '[bed][side]sidechaincompress=threshold=0.02:ratio=4:attack=25:release=500[ducked];'
            f"[ducked]aeval=exprs='val(0)*{mask}|val(1)*{mask}':channel_layout=stereo[gated];"
            '[voice][gated]amix=inputs=2:duration=first:normalize=0,'
            'alimiter=limit=0.60:level=0:latency=1[outa]')
        try:
            _ffmpeg(['-i',source,'-stream_loop','-1','-i',self.audio,'-filter_complex_threads','1',
                     '-filter_complex',graph,'-map','0:v:0','-map','[outa]','-map_metadata','0',
                     '-map_chapters','0','-t',f'{duration:.6f}','-c:v','copy','-c:a','aac',
                     '-ar','48000','-ac','2','-b:a','160k','-movflags','+faststart',target])
            peak=true_peak(target)
            if peak>-3:raise ValueError(f'Mixed video true peak exceeds -3 dB: {peak}')
        except BaseException:
            target.unlink(missing_ok=True)
            raise
        self.receipt.update(status='mixed_requires_video_validation',
                            mix=dict(target_lufs=-28,ducking=True,sample_accurate_muted_intervals=muted,
                                     video_stream_copied=True,original_input_preserved=True,
                                     measured_true_peak_db=peak,true_peak_ceiling_db=-3))
        return self.receipt

    def commit(self,video):
        # Callers seal receipt/manifest first. No download I/O remains after the
        # final atomic history write, so late cache errors cannot consume a song.
        if not self._cleaned:self._clean()
        assignment=self.rotation.commit(self.day,sha256(video))
        self.receipt.update(status='committed',selection=assignment,video_sha256=assignment['video_sha256'])
        return copy.deepcopy(self.receipt)
