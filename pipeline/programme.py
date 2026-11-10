"""Edition-bound overview cards and silent category interludes."""
import subprocess
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import imageio_ffmpeg
from .core import ROOT, read_json, sha256

FFMPEG=imageio_ffmpeg.get_ffmpeg_exe()


def section_cards(edition):
    labels={s['id']:s['name'] for s in read_json(ROOT/'config/pipeline.json')['editorial_policy']['sections']}
    cards=[]
    for story in edition['stories']:
        section=story['section']
        if not cards or cards[-1]['id']!=section:
            cards.append(dict(id=section,title=labels[section],titles=[]))
        cards[-1]['titles'].append(story['title'])
    return cards


def draw_overview(card, path):
    image=Image.new('RGB',(1440,640),'#f8f7ee');d=ImageDraw.Draw(image)
    small=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',30)
    font=ImageFont.truetype('C:/Windows/Fonts/msyhbd.ttc',44)
    d.text((55,30),'NJAU-CEA  /  本期新闻目录',font=small,fill='#4c7667')
    for i,title in enumerate(card['titles']):
        y=105+i*170
        d.rounded_rectangle((40,y,1400,y+145),radius=20,fill='#ffffff',outline='#b8cbc0',width=2)
        d.rounded_rectangle((65,y+40,76,y+104),radius=4,fill='#8ea85b')
        size=44
        while size>32 and d.textbbox((0,0),title,font=ImageFont.truetype('C:/Windows/Fonts/msyhbd.ttc',size))[2]>1260:size-=1
        d.text((105,y+45),title,font=ImageFont.truetype('C:/Windows/Fonts/msyhbd.ttc',size),fill='#173f3d')
    image.save(path)


def draw_category_card(card, path, background):
    # Rebuild the clean campus underlay instead of revealing the old baked-in
    # slogan. Its mask follows the original 1244→994 diagonal, never a rectangle.
    width,height=1920,1080
    with Image.open(background) as source:
        sw=min(source.width,source.height*16/9);sh=sw*9/16
        box=((source.width-sw)/2,(source.height-sh)/2,(source.width+sw)/2,(source.height+sh)/2)
        campus=source.convert('RGBA').crop(box).resize((640,360),Image.Resampling.NEAREST).resize((width,height),Image.Resampling.NEAREST)
    image=Image.new('RGBA',(width,height),(0,0,0,0))
    tint=Image.new('RGBA',(width,height),'#133c35')
    # Left→right: low transparency to high transparency, with a stronger reveal
    # near the diagonal. Keep the text side dark enough for white lettering.
    alpha=bytearray(width*height);mask=bytearray(width*height)
    for y in range(height):
        edge=1244-250*y/height
        for x in range(min(width,int(edge)+1)):
            u=x/edge
            opacity=.97-.76*(max(0,(u-.35)/.65)**1.45)
            alpha[y*width+x]=round(opacity*255)
            mask[y*width+x]=255
    tint.putalpha(Image.frombytes('L',(width,height),bytes(alpha)))
    image=Image.alpha_composite(campus,tint)
    image.putalpha(Image.frombytes('L',(width,height),bytes(mask)))
    d=ImageDraw.Draw(image)
    # Preserve the complete 36 px lime divider, including the lower-left end.
    d.polygon([(1244,0),(1280,0),(1030,1080),(994,1080)],fill='#d7e78a')
    def text(x,y,value,size,color='#fff9e9'):
        d.text((x,y),value,font=ImageFont.truetype('C:/Windows/Fonts/msyhbd.ttc',size),fill=color,stroke_width=1,stroke_fill='#173f3d')
    text(80,85,'NJAU-CEA 新闻联播',42)
    text(80,220,'接下来',38,'#d7e78a')
    title=card['title'].replace('GitHub昨日开源有趣项目','GitHub 开源项目')
    text(80,285,title,66)
    d.line((80,390,990,390),fill='#789386',width=2)
    for i,title in enumerate(card['titles']):
        size=38
        while size>28 and d.textbbox((0,0),title,font=ImageFont.truetype('C:/Windows/Fonts/msyhbd.ttc',size))[2]>870:size-=1
        y=450+i*155
        d.ellipse((82,y+15,94,y+27),fill='#d7e78a')
        text(112,y,title,size)
    text(80,985,'校园科技 · 青年视角',28,'#b6d1c1')
    image.save(path)


def compose_transition_frame(scene,coverage,frame,previous,following):
    """One coverage mask moves the entire card, including its left typography."""
    layer=scene.copy().convert('RGBA');draw=ImageDraw.Draw(layer)
    def ease(value):
        value=max(0,min(1,value));return value*value*(3-2*value)
    # Preserve the source sweep's original leading/trailing accent ribbons.
    if frame<22:
        edge=-240+2400*ease(frame/22)
        draw.polygon([(edge+106,0),(edge+160,0),(edge-160,1080),(edge-214,1080)],fill='#d7e78a')
        draw.polygon([(edge+84,0),(edge+106,0),(edge-214,1080),(edge-236,1080)],fill='#f9f5e9')
    elif frame>58:
        edge=-240+2400*ease((frame-58)/25)
        draw.polygon([(edge+160,0),(edge+206,0),(edge-114,1080),(edge-160,1080)],fill='#d7e78a')
    layer.putalpha(coverage)
    backdrop=previous if frame<42 else following
    return Image.alpha_composite(backdrop.convert('RGBA'),layer).convert('RGB')


def context_footer(image,title):
    """Keep the lower-third frame/logo; replace only its spoken sentence."""
    image=image.convert('RGB').copy();draw=ImageDraw.Draw(image)
    draw.rectangle((326,938,1919,1037),fill='#f8f7ee')
    draw.text((350,961),'导视',font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',32),fill='#4c7667')
    text='接下来 · '+title.replace('GitHub昨日开源有趣项目','GitHub 开源项目')
    size=64
    while size>40 and draw.textbbox((0,0),text,font=ImageFont.truetype('C:/Windows/Fonts/msyhbd.ttc',size))[2]>1400:size-=1
    draw.text((470,943),text,font=ImageFont.truetype('C:/Windows/Fonts/msyhbd.ttc',size),fill='#133c35')
    return image


def _context_frame(clip,path,tail=False,title='下一栏目'):
    if clip is None:return Image.new('RGB',(1920,1080),'#f8f7ee')
    # Retain the existing programme mark, source row and empty ticker frame.
    # Only the body caption changes to a category guide during the silent gap.
    args=[FFMPEG,'-v','error','-y','-threads','2']
    if tail:args+=['-sseof','-0.15']
    args+=['-i',clip]
    if tail:args+=['-vf','reverse']
    result=subprocess.run(list(map(str,[*args,'-frames:v','1',path])),capture_output=True)
    if result.returncode:raise RuntimeError(result.stderr.decode('utf8',errors='replace')[-3000:])
    with Image.open(path) as image:result=context_footer(image,title)
    result.save(path)
    return result


def render_interlude(event,card,library,output,previous_clip=None,next_clip=None):
    output=Path(output);plate=output.with_suffix('.png')
    item=next(x for x in library['items'] if x['webm']==event['webm'])
    draw_category_card(card,plate,Path(library['_root'])/item['art'])
    asset=Path(library['_root'])/event['webm']
    if sha256(asset)!=event['sha256']:raise ValueError('转场素材变化')
    full=output.with_name(output.stem+'-complete-card.png')
    result=subprocess.run(list(map(str,[FFMPEG,'-v','error','-y','-threads','2','-c:v','libvpx-vp9','-i',asset,
        '-vf','select=eq(n\\,42)','-frames:v','1',full])),capture_output=True)
    if result.returncode:raise RuntimeError(result.stderr.decode('utf8',errors='replace')[-3000:])
    with Image.open(full) as source,Image.open(plate) as overlay:
        scene=Image.alpha_composite(source.convert('RGBA'),overlay.convert('RGBA'))
    # The library's right header contains a baked historical abbreviation.
    # Replace it before applying the shared whole-card coverage mask.
    brand_draw=ImageDraw.Draw(scene)
    brand_draw.rectangle((1590,82,1919,197),fill='#f9f5e9')
    brand_draw.text((1610,113),'NJAU-CEA',font=ImageFont.truetype('C:/Windows/Fonts/msyhbd.ttc',38),fill='#346450')
    scene.save(full)
    previous=_context_frame(previous_clip,output.with_name(output.stem+'-previous.png'),tail=True,title=card['title'])
    following=_context_frame(next_clip,output.with_name(output.stem+'-next.png'),title=card['title'])
    # Original source alpha drives both halves. Only complete frames are sent to
    # the encoder; no static left layer is composited after the sweep.
    decoder_args=[FFMPEG,'-v','error','-threads','2','-c:v','libvpx-vp9','-i',asset,'-f','rawvideo','-pix_fmt','rgba','-']
    encoder_args=[FFMPEG,'-v','error','-y','-f','rawvideo','-pix_fmt','rgb24','-s','1920x1080','-r','30','-i','-',
        '-an','-frames:v','102','-c:v','libx264','-preset','veryfast','-crf','18','-pix_fmt','yuv420p','-threads','2',output]
    with output.with_suffix('.decode.log').open('wb') as decode_log,output.with_suffix('.encode.log').open('wb') as encode_log:
        decoder=subprocess.Popen(list(map(str,decoder_args)),stdout=subprocess.PIPE,stderr=decode_log)
        encoder=subprocess.Popen(list(map(str,encoder_args)),stdin=subprocess.PIPE,stderr=encode_log)
        try:
            for _ in range(9):encoder.stdin.write(previous.tobytes())
            for frame in range(84):
                raw=decoder.stdout.read(1920*1080*4)
                if len(raw)!=1920*1080*4:raise ValueError('原转场不足84帧，停止导出')
                coverage=Image.frombytes('RGBA',(1920,1080),raw).getchannel('A')
                encoder.stdin.write(compose_transition_frame(scene,coverage,frame,previous,following).tobytes())
            for _ in range(9):encoder.stdin.write(following.tobytes())
            encoder.stdin.close();decoder.stdout.close()
            if decoder.wait()!=0 or encoder.wait()!=0:raise RuntimeError('整体转场编码失败，详见本次日志')
        except BaseException:
            for process in [decoder,encoder]:
                if process.poll() is None:process.kill()
            raise
    return output


def insert_interludes(shots,cues,clips,edition,library,plan,run_dir):
    """Insert complete silent clips between category bodies, never over narration."""
    cards={c['id']:c for c in section_cards(edition)}
    selections=iter(plan['transitions']);events=[];interludes=[];assembly=[];offset=0
    previous_section=None
    for i,(shot,cue,clip) in enumerate(zip(shots,cues,clips)):
        section=edition['stories'][shot['scene']]['section'] if shot['scene']>=0 else None
        if section and previous_section and section!=previous_section:
            event=next(selections).copy();start=cue['start']+offset
            event.update(from_frame=round((start+.3)*30),cut_frame=round((start+1.7)*30),frames=84,
                         interlude_start=start,interlude_end=start+3.4)
            gap=render_interlude(event,cards[section],library,Path(run_dir)/f'interlude-{len(events):02d}.mp4',previous_clip=clips[i-1],next_clip=clip)
            assembly.append(dict(path=gap,seconds=3.4,kind='silence'))
            interludes.append(dict(start=start,end=start+3.4,kind='category',section=section,
                title=cards[section]['title'],titles=cards[section]['titles'],lead_seconds=.3,sweep_seconds=2.8,tail_seconds=.3))
            events.append(event);offset+=3.4
        cue['start']+=offset;cue['end']+=offset
        shot.update(start=cue['start'],end=cue['end'])
        assembly.append(dict(path=clip,cue=i,seconds=shot['duration'],kind='speech'))
        if section:previous_section=section
    try:next(selections)
    except StopIteration:pass
    else:raise ValueError('栏目转场数量与实际边界不符')
    frozen=dict(plan,transitions=events,total_frames=round(cues[-1]['end']*30),mode='inserted_silent_interludes')
    return assembly,interludes,frozen
