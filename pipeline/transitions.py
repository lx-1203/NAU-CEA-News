"""Randomly assign campus stingers once, then render their frozen frame plan."""
import argparse
import hashlib
import json
import random
import secrets
import shutil
import subprocess
import tempfile
from pathlib import Path

import imageio_ffmpeg

ROOT=Path(__file__).resolve().parents[1]
DEFAULT_LIBRARY=ROOT/'assets/transitions/campus-ip-sweep-v4/library.json'
FFMPEG=imageio_ffmpeg.get_ffmpeg_exe()


def sha(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def choose_variants(ids,count,seed=None):
    if count<0 or len(ids)!=len(set(ids)) or (count and not ids):
        raise ValueError('转场库为空、ID重复或抽取数量无效')
    seed=secrets.randbits(64) if seed is None else seed
    rng=random.Random(seed);selected=[]
    while len(selected)<count:
        bag=list(ids);rng.shuffle(bag)
        if selected and len(bag)>1 and bag[0]==selected[-1]:bag[0],bag[1]=bag[1],bag[0]
        selected.extend(bag[:count-len(selected)])
    return {'seed':seed,'ids':selected}


def load_library(path=DEFAULT_LIBRARY):
    path=Path(path).resolve()
    data=json.loads(path.read_text(encoding='utf-8'))
    if not data.get('enabled'):raise ValueError('转场库尚未启用')
    if (data.get('width'),data.get('height'),data.get('fps'),data.get('frames'),data.get('cut_frame'))!=(1920,1080,30,84,42):
        raise ValueError('转场库格式不是1920×1080/30fps/84帧/42帧切点')
    ids=[item['id'] for item in data['items']]
    if not ids or len(ids)!=len(set(ids)):raise ValueError('转场库为空或ID重复')
    data['_root']=str(path.parent);data['_path']=str(path)
    for item in data['items']:
        media=(path.parent/item['webm']).resolve()
        if not media.is_relative_to(path.parent):raise ValueError('转场文件超出素材库目录')
        if sha(media)!=item['sha256']:raise ValueError(f'转场文件校验失败：{item["id"]}')
        if item.get('art'):
            background=(path.parent/item['art']).resolve()
            if not background.is_relative_to(path.parent):raise ValueError('校园底图超出素材库目录')
            if item.get('art_sha256') and sha(background)!=item['art_sha256']:raise ValueError('校园底图校验失败：'+item['id'])
    return data


def library_dependencies(library):
    return [Path(library['_path']),*[Path(library['_root'])/x['webm'] for x in library['items']],
            *[Path(library['_root'])/x['art'] for x in library['items'] if x.get('art')]]


def validate_broadcast_band(value):
    if value is None:return None
    if not isinstance(value,dict) or any(type(value.get(k)) is not int for k in ['x','y','width','height']):
        raise ValueError('播报条保留区域需为整数像素矩形')
    x,y,w,h=(value[k] for k in ['x','y','width','height'])
    if not (x>=0 and y>=0 and w>0 and h>0 and x+w<=1920 and y+h<=1080):
        raise ValueError('播报条保留区域超出画布')
    return dict(x=x,y=y,width=w,height=h)


def make_plan(timeline,library,seed=None,broadcast_band=None,sections=None):
    fps=library['fps'];frames=library['frames'];cut=library['cut_frame']
    shots=timeline['shots']
    if timeline['fps']!=fps or not shots:raise ValueError('时间线帧率或镜头列表无效')
    total=round(shots[-1]['end']*fps);boundaries=[];section_edges={}
    if sections is not None and (not isinstance(sections,list) or not sections or any(not isinstance(x,str) or not x.strip() for x in sections)):
        raise ValueError('栏目转场需要完整栏目列表')
    previous_end=0
    for i,shot in enumerate(shots):
        start,end=round(shot['start']*fps),round(shot['end']*fps)
        if start!=previous_end or end<=start:raise ValueError('时间线镜头不连续或长度无效')
        previous_end=end
        if i and shot['scene']!=shots[i-1]['scene']:
            previous_scene,scene=shots[i-1]['scene'],shot['scene']
            if sections is not None:
                if previous_scene<0 or scene<0:continue
                if max(previous_scene,scene)>=len(sections):raise ValueError('新闻镜头超出栏目列表')
                if sections[previous_scene]==sections[scene]:continue
                section_edges[start]=dict(from_section=sections[previous_scene],to_section=sections[scene])
            boundaries.append(start)
    if any(b-cut<0 or b-cut+frames>total for b in boundaries):raise ValueError('转场超出成片首尾')
    if any(b-a<frames for a,b in zip(boundaries,boundaries[1:])):raise ValueError('相邻转场时间重叠')
    choice=choose_variants([x['id'] for x in library['items']],len(boundaries),seed)
    items={x['id']:x for x in library['items']}
    transitions=[dict(id=key,webm=items[key]['webm'],from_frame=b-cut,cut_frame=b,frames=frames,
                      sha256=items[key].get('sha256'),**section_edges.get(b,{})) for b,key in zip(boundaries,choice['ids'])]
    result={'version':2,'fps':fps,'seed':choice['seed'],'total_frames':total,
            'policy':'shuffle-bag; no adjacent repeats when library has multiple items',
            'transitions':transitions}
    band=validate_broadcast_band(broadcast_band)
    if band:result['broadcast_band']=band
    result['boundary_scope']='section' if sections is not None else 'scene'
    return result


def run(args):
    result=subprocess.run([str(x) for x in args],capture_output=True)
    if result.returncode:raise RuntimeError(result.stderr.decode('utf-8',errors='replace')[-6000:])
    return result


def compose_transitions(source,output,plan,library):
    source,output=Path(source).resolve(),Path(output).resolve()
    if source==output:raise ValueError('不能覆盖原成片')
    if output.exists():raise FileExistsError(output)
    output.parent.mkdir(parents=True,exist_ok=True)
    # All cue frames have the same size/pixel format. A change of H264 colour
    # tags at an original-video cue must not restart the scheduled overlay graph.
    fps=library['fps'];inputs=['-reinit_filter','0','-i',source];graph=[];back='0:v'
    band=validate_broadcast_band(plan.get('broadcast_band'))
    if band:
        graph.append('[0:v]split=2[programme][band_source]');back='programme'
    for i,event in enumerate(plan['transitions'],1):
        media=Path(library['_root'])/event['webm']
        if sha(media)!=event['sha256']:raise ValueError('已规划的转场文件发生变化')
        inputs.extend(['-threads','2','-c:v','libvpx-vp9','-i',media])
        start=event['from_frame']/fps;end=(event['from_frame']+event['frames'])/fps
        graph.append(f'[{i}:v]setpts=PTS-STARTPTS+{start:.9f}/TB[tr{i}]')
        graph.append(f"[{back}][tr{i}]overlay=eof_action=pass:repeatlast=0:format=auto:enable='gte(t,{start:.9f})*lt(t,{end:.9f})'[out{i}]")
        back=f'out{i}'
    if band:
        x,y,w,h=(band[k] for k in ['x','y','width','height'])
        graph.append(f'[band_source]crop={w}:{h}:{x}:{y}[broadcast_band]')
        graph.append(f'[{back}][broadcast_band]overlay={x}:{y}:format=auto[with_broadcast_band]')
        back='with_broadcast_band'
    with tempfile.NamedTemporaryFile(prefix=output.stem+'-partial-',suffix='.mp4',dir=output.parent,delete=False) as tmp:
        temporary=Path(tmp.name)
    try:
        if not plan['transitions']:shutil.copy2(source,temporary)
        else:
            run([FFMPEG,'-v','error','-y',*inputs,'-filter_complex_threads','1','-filter_complex',';'.join(graph),
                 '-map',f'[{back}]','-map','0:a?','-c:v','libx264','-preset','veryfast','-crf','18',
                 '-pix_fmt','yuv420p','-r',fps,'-c:a','copy','-frames:v',plan['total_frames'],
                 '-threads','2','-movflags','+faststart',temporary])
        run([FFMPEG,'-v','error','-i',temporary,'-f','null','-'])
        reader=imageio_ffmpeg.read_frames(str(temporary));meta=next(reader);reader.close()
        if meta['size']!=(1920,1080) or abs(meta['fps']-fps)>.01 or abs(meta['duration']-plan['total_frames']/fps)>.05:
            raise ValueError('合成后尺寸/帧率/时长发生变化')
        # Preserve either the exact original audio packets, or the absence of audio.
        source_reader=imageio_ffmpeg.read_frames(str(source));source_meta=next(source_reader);source_reader.close()
        audio_present=bool(source_meta.get('audio_codec'))
        if audio_present!=bool(meta.get('audio_codec')):raise ValueError('合成改变了原音轨的有无')
        packet_hash=[]
        if audio_present:
            for media in [source,temporary]:
                result=run([FFMPEG,'-v','error','-i',media,'-map','0:a:0','-c:a','copy','-vn','-f','hash','-hash','sha256','-'])
                packet_hash.append(result.stdout.decode().strip())
        else:packet_hash=[None,None]
        if packet_hash[0]!=packet_hash[1]:raise ValueError('合成改变了原音轨数据')
        temporary.replace(output)
        return {'video':str(output),'sha256':sha(output),'audio_packets_unchanged':True,'audio_present':audio_present,'broadcast_band_preserved':bool(band),
                'source':str(source),'source_sha256':sha(source),'metadata':meta,'plan':plan}
    except Exception:
        if temporary.exists():temporary.unlink()
        raise


def main():
    parser=argparse.ArgumentParser(description='Apply random campus pixel stingers without changing narration timing')
    parser.add_argument('--video',type=Path,required=True);parser.add_argument('--timeline',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--library',type=Path,default=DEFAULT_LIBRARY)
    parser.add_argument('--seed',type=int)
    args=parser.parse_args();library=load_library(args.library)
    plan=make_plan(json.loads(args.timeline.read_text(encoding='utf-8')),library,args.seed)
    receipt=compose_transitions(args.video,args.output,plan,library)
    args.output.with_suffix('.transitions.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'output':str(args.output),'transitions':len(plan['transitions']),'seed':plan['seed']},ensure_ascii=False))


if __name__=='__main__':main()
