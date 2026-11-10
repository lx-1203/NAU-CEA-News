"""Measured news pacing, preserving source WAV and pitch; no model or GPU."""
import array
import math
import re
import shutil
import subprocess
import sys
import wave
from pathlib import Path

import imageio_ffmpeg
from .core import sha256

DIGITS='零一二三四五六七八九'


def _integer(n):
    if n>=10000:
        high,low=divmod(n,10000)
        return _integer(high)+'万'+(('零' if low<1000 else '')+_integer(low) if low else '')
    if n==0:return '零'
    result='';pending=False
    for value,label in [(1000,'千'),(100,'百'),(10,'十'),(1,'')]:
        digit,n=divmod(n,value)
        if digit:
            if pending:result+='零'
            result+=DIGITS[digit]+label;pending=False
        elif result and n:pending=True
    return result[1:] if result.startswith('一十') else result


def spoken_units(text, spoken_text=None):
    text=spoken_text if spoken_text is not None else text
    if not isinstance(text,str) or not text.strip():raise ValueError('实际读音必须是非空文本')
    if re.search(r'\d\s*[-–—/:]\s*\d|(?:^|[^0-9])[+-]\d',text):
        raise ValueError('日期/区间/比例/正负数需提供展开后的spoken_text')
    text=re.sub(r'\d{1,3}(?:,\d{3})+',lambda m:m[0].replace(',',''),text)
    # Year strings use separate digits; ordinary quantities use cardinal numbers.
    text=re.sub(r'(?<!\d)\d{4}(?=年)',lambda m:''.join('〇' if c=='0' else DIGITS[int(c)] for c in m[0]),text)
    text=re.sub(r'(\d+(?:\.\d+)?)%',lambda m:'百分之'+_numeric_value(m[1]),text)
    text=re.sub(r'\d+(?:\.\d+)?',lambda m:_numeric_value(m[0]),text)
    if re.search(r'[a-z]',text):raise ValueError('英文名称需用spoken_text注明实际读音，不能按拼写字数猜语速')
    count=len(re.findall(r'[\u3400-\u9fff〇A-Z]',text))
    if count==0:raise ValueError('口播缺少可计数的读音')
    return count


def _numeric_value(value):
    parts=value.split('.')
    if len(parts[0])>8:raise ValueError('长数字需提供实际spoken_text读法')
    return _integer(int(parts[0]))+('点'+''.join(DIGITS[int(c)] for c in parts[1]) if len(parts)>1 else '')


def target_cpm(text, policy, sensitive=None):
    detected=bool(re.search(r'\d|[〇零一二三四五六七八九十百千万亿两]+(?:年|月|日|天|台|个|分钟|秒|%)',text))
    detected=detected or any(t in text for t in policy.get('terms',[]))
    sensitive=bool(sensitive) or detected
    return float(policy.get('sensitive_cpm',285) if sensitive else policy.get('normal_cpm',295))


def _read(path):
    with wave.open(str(path)) as w:
        if w.getsampwidth()!=2 or w.getnchannels()!=1:raise ValueError('语速处理需16-bit单声道PCM')
        rate=w.getframerate();raw=w.readframes(w.getnframes())
    values=array.array('h',raw)
    if sys.byteorder!='little':values.byteswap()
    return rate,values,raw


def _bounds(values,rate,threshold_db=-45):
    window=max(1,round(rate*.01));threshold=32768*10**(threshold_db/20)
    active=[]
    for i in range(0,len(values),window):
        chunk=values[i:i+window]
        rms=math.sqrt(sum(x*x for x in chunk)/len(chunk))
        if rms>threshold:active.append(i)
    if not active:raise ValueError('配音静音或没有可靠发声，停止语速处理')
    # Retain 60ms protection around detected phonetic edges, not a hard word cut.
    guard=round(rate*.06)
    return max(0,active[0]-guard),min(len(values),active[-1]+window+guard)


def pace_wav(source,target,text,policy,extra_gap=.22,spoken_text=None,sensitive=None,fps=30):
    source,target=Path(source),Path(target)
    if source.resolve()==target.resolve():raise ValueError('语速处理必须保留源录音')
    if not math.isfinite(extra_gap) or extra_gap<0:raise ValueError('句尾留白必须非负')
    if not math.isfinite(fps) or fps<=0:raise ValueError('帧率必须为正数')
    units=spoken_units(text,spoken_text)
    cpm=target_cpm(text,policy,sensitive)
    preferred_cpm=cpm
    minimum=float(policy.get('min_cpm',280));maximum=float(policy.get('max_cpm',300))
    if not 0<minimum<=cpm<=maximum:raise ValueError('语速目标不在允许范围内')
    rate,values,_=_read(source);start,end=_bounds(values,rate,policy.get('threshold_db',-45))
    # The renderer adds extra_gap then rounds up to a video frame. Include this
    # in the speed contract so short sentence padding cannot quietly slow a film.
    planned_total=units*60/cpm
    desired=planned_total-extra_gap
    padding=.04+.06
    if desired<=padding+.10:raise ValueError('句子太短，不可强制套用统一语速；合并语义完整句后处理')
    factor=((end-start)/rate)/(desired-padding)
    maximum_tempo=float(policy.get('max_tempo',1.60))
    if factor>maximum_tempo:
        achievable=math.floor(units*60/(((end-start)/rate)/maximum_tempo+padding+extra_gap))
        if achievable>=minimum:
            cpm=min(cpm,achievable)
            desired=units*60/cpm-extra_gap
            factor=((end-start)/rate)/(desired-padding)
    if not float(policy.get('min_tempo',.75))<=factor<=float(policy.get('max_tempo',1.60)):
        raise ValueError(f'变速倍率{factor:.3f}超过清晰度边界，需要重录或调整停顿')
    before=sha256(source)
    temp=target.with_name(target.stem+'-trim-input.wav')
    target.parent.mkdir(parents=True,exist_ok=True)
    with wave.open(str(temp),'wb') as w:
        w.setparams((1,2,rate,0,'NONE','not compressed'));w.writeframes(values[start:end].tobytes())
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-v','error','-y','-i',str(temp),'-af',
        f'atempo={factor:.9f},adelay=40,apad=pad_dur=0.06','-ar',str(rate),'-ac','1',str(target)],
        check=True,capture_output=True,timeout=60)
    out_rate,out_values,_=_read(target)
    output_seconds=len(out_values)/out_rate
    # atempo has bounded block rounding; do not truncate speech to forge a duration.
    slot=math.ceil((output_seconds+extra_gap)*fps)/fps
    actual=units*60/slot
    if not minimum<=actual<=maximum:
        raise ValueError(f'实测字速{actual:.2f}未在{minimum:g}–{maximum:g}内；保留产物供检查')
    if sha256(source)!=before:raise ValueError('源录音发生变化')
    return dict(spoken_units=units,target_cpm=cpm,preferred_cpm=preferred_cpm,effective_cpm=actual,tempo=factor,
                input_seconds=len(values)/rate,trim_start=start/rate,trim_end=end/rate,
                output_seconds=output_seconds,extra_gap_seconds=extra_gap,slot_seconds=slot,
                source_file=source.name,source_sha256=before,output_sha256=sha256(target),pitch_shift_semitones=0,
                engine='FFmpeg atempo (pitch-preserving)',sensitive_sentence=preferred_cpm==float(policy.get('sensitive_cpm',285)))


def pace_for_render(path,line,policy,fps=30):
    if not policy.get('enabled',False):return None
    path=Path(path)
    original=path.with_name(path.stem+'-unpaced.wav')
    shutil.copy2(path,original)
    return pace_wav(original,path,line['text'],policy,fps=fps,
                    spoken_text=line.get('spoken_text'),sensitive=line.get('sensitive'))


def pacing_summary(shots,policy):
    report={}
    for anchor in ['all','xiaoXu','xiaoHe']:
        selected=[s for s in shots if s['scene']>=0 and (anchor=='all' or s['anchor']==anchor)]
        if not selected:continue
        if any(not s.get('pacing') for s in selected):raise ValueError('正文配音缺少语速收据')
        units=sum(s['pacing']['spoken_units'] for s in selected)
        seconds=sum(s['duration'] for s in selected)
        cpm=units*60/seconds
        if not float(policy.get('min_cpm',280))<=cpm<=float(policy.get('max_cpm',300)):
            raise ValueError(f'{anchor}正文实测字速{cpm:.2f}超出目标')
        report[anchor]=dict(spoken_units=units,seconds=seconds,cpm=cpm,sentences=len(selected))
    if not report:raise ValueError('没有正文配音，不能声称语速验收通过')
    return dict(status='passed',scope='body includes sentence-internal pauses and video cue padding; excludes intro/outro/transitions',anchors=report)
