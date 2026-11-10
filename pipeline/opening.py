"""Integrate an explicitly approved opening without regenerating narration."""
import copy
import hashlib
import math
import subprocess
import tempfile
from pathlib import Path

import imageio_ffmpeg
from .core import read_json, sha256

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()


def load_opening(config):
    setting = config.get('opening', {})
    if not setting.get('enabled'):
        return None
    approval = Path(setting['approval']).resolve()
    data = read_json(approval)
    if data.get('status') != 'approved_for_use' or data.get('placement') != '双主播演播室开场前':
        raise ValueError('开屏尚未获得当前接入位置的确认')
    if data.get('size') != [1920,1080] or data.get('fps') != 30 or data.get('duration_seconds') != 8:
        raise ValueError('开屏必须为已确认的1080p30八秒版本')
    for key in ['video','silent_video','credits_file']:
        data[key]=str((approval.parent/Path(data[key])).resolve())
    for key in ['video', 'silent_video']:
        if sha256(Path(data[key])) != data[key+'_sha256']:
            raise ValueError('已确认开屏文件哈希变化：'+key)
    if not Path(data['credits_file']).is_file():
        raise ValueError('开屏缺少配乐署名文件')
    return dict(data, approval=str(approval))


def opening_dependencies(opening):
    return [Path(opening[k]) for k in ['approval','video','silent_video','credits_file']] if opening else []


def shift_timeline(timeline, opening):
    """Offsets programme coordinates; local per-cue action times stay unchanged."""
    result = copy.deepcopy(timeline)
    offset = opening['duration_seconds']
    if not isinstance(offset,(int,float)) or not math.isfinite(offset) or offset <= 0:
        raise ValueError('开屏时长无效')
    if not result['shots'] or abs(result['shots'][0]['start']) > .0001:
        raise ValueError('只能对零起点节目接入一次开屏')
    for shot in result['shots']:
        shot['start'] += offset
        shot['end'] += offset
    for interlude in result.get('interludes',[]):
        interlude['start'] += offset
        interlude['end'] += offset
    if result.get('transitions'):
        plan = result['transitions']
        frames = round(offset*result['fps'])
        plan['total_frames'] += frames
        for event in plan['transitions']:
            event['from_frame'] += frames
            event['cut_frame'] += frames
            for key in ['interlude_start','interlude_end']:
                if key in event:event[key] += offset
    result['opening'] = dict(start=0,end=offset,title='地球开屏',
        video=opening['video'],sha256=opening['video_sha256'])
    return result


def _run(args):
    result = subprocess.run([str(x) for x in args],capture_output=True)
    if result.returncode:
        raise RuntimeError(result.stderr.decode('utf8',errors='replace')[-5000:])
    return result


def prepend_opening(body, target, opening, silent=False):
    """Stream-copy compatible approved assets, preserving every body AAC packet."""
    body,target = Path(body).resolve(),Path(target).resolve()
    intro = Path(opening['silent_video' if silent else 'video']).resolve()
    if target.exists() or body == target:
        raise FileExistsError(target)
    # The silent asset has no audio: add eight seconds of silent AAC, never mute
    # the programme itself. This alternative is built from the same timeline.
    with tempfile.TemporaryDirectory(prefix='opening-',dir=target.parent) as temporary:
        temp = Path(temporary)
        if silent:
            silent_intro = temp/'silent-with-audio.mp4'
            _run([FFMPEG,'-v','error','-i',intro,'-f','lavfi','-i','anullsrc=r=48000:cl=stereo',
                  '-t',8,'-map','0:v','-map','1:a','-c:v','copy','-c:a','aac','-b:a','160k',silent_intro])
            intro = silent_intro
        playlist = temp/'concat.txt'
        escaped = [str(p).replace("'", "'\\''") for p in [intro,body]]
        playlist.write_text(''.join("file '"+p+"'\n" for p in escaped),encoding='utf8')
        _run([FFMPEG,'-v','error','-f','concat','-safe',0,'-i',playlist,
              '-map','0:v:0','-map','0:a:0','-map_metadata',-1,'-map_chapters',-1,
              '-c','copy','-movflags','+faststart',target])
    # Raw compressed packets must contain the unchanged complete body suffix.
    def packets(path, stream):
        return _run([FFMPEG,'-v','error','-i',path,'-map',stream,'-c','copy','-f','data','-']).stdout
    original = packets(body,'0:a:0')
    if not packets(target,'0:a:0').endswith(original):
        raise ValueError('接入开屏改变了原主播AAC数据')
    return dict(opening=str(intro) if not silent else opening['silent_video'],
        opening_sha256=opening['silent_video_sha256' if silent else 'video_sha256'],
        offset_seconds=opening['duration_seconds'],body=str(body),body_sha256=sha256(body),
        body_aac_sha256=hashlib.sha256(original).hexdigest(),body_aac_packets_unchanged=True,
        body_video_stream_copied=True,silent_opening=silent,
        video_packet_note='Concat may inject H264 parameter sets; verify decoded body frames, not raw packet suffix.')
