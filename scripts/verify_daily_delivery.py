"""Inspect a rendered edition, its audio lineage, navigation and actual frames."""
import sys,json,subprocess,wave,math
from pathlib import Path
from array import array
from PIL import Image,ImageDraw
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from pipeline.core import ROOT,read_json,write_json,sha256
from pipeline.workbench import edition_lines
from pipeline.performance import performance_audit
from pipeline.production import performance_events, validate_anchor_library
from pipeline.render import FFMPEG,timestamp
from pipeline.programme import section_cards
from pipeline.navigation import build_navigation

run=Path(sys.argv[1]).resolve()
out=Path(sys.argv[2]).resolve() if len(sys.argv)>2 else run/'delivery-qa'
out.mkdir(parents=True,exist_ok=True)
if any(out.glob('frame-*.jpg')):
 raise FileExistsError(f'Use an empty frame-output directory: {out}')
e=read_json(run/'edition.json');t=read_json(run/'timeline.json');m=read_json(run/'manifest.json')
shots=t['shots'];gaps=t['interludes'];cards=section_cards(e);lines=edition_lines(e)
if t.get('outro'):
 lines=[line for line in lines if line['scene'] != -2]
validate_anchor_library()
plan=read_json(run/'production-plan.json')
assert len(plan['shots'])==len(shots)
assert len(shots)==len(lines) and len(gaps)==len(cards)-1
assert build_navigation(e,t)==read_json(run/'chapters.json')
assert e['title']==read_json(ROOT/'config/pipeline.json')['programme']['brand'] and t['opening']['end']==8
for path,h in m['source_hashes'].items():assert sha256(ROOT/path)==h,path
for path,h in m['audio_inputs'].items():assert sha256(path)==h,path
for path,h in m['files'].items():assert sha256(run/path)==h,path
audio=read_json(run/'audio-manifest.json');cfg=read_json(ROOT/'config/pipeline.json')
for i,(s,line) in enumerate(zip(shots,lines)):
 assert s['text']==line['text'] and s['anchor']==line['anchor']
 assert sha256(audio[str(i)]['path'])==audio[str(i)]['sha256']
 assert cfg['speech']['workbench']['voices'][s['anchor']]['name'] in s['voice']
 assert s['performance_events']==performance_events(line,s['raw_duration'],s['speech_intervals'],plan['shots'][i]['performance'])
 assert s['performance_events'][0]['expression']==s['performance_events'][-1]['expression']
 assert s['speech_intervals'][0][0]<s['performance_events'][1]['at']<s['speech_intervals'][-1][1]
blocks=(run/'subtitles.srt').read_text('utf-8-sig').strip().split('\n\n')
captions=[*shots,*t.get('outro',{}).get('lines',[])]
assert len(blocks)==len(captions)
for b,s in zip(blocks,captions):
 assert b.splitlines()[1]==f'{timestamp(s["start"])} --> {timestamp(s["end"])}'
 assert b.splitlines()[2]==s['text']
overviews=[s for s in shots if s.get('kind')=='overview']
assert len(overviews)==len(cards) and all(s['duration']>=6.5 for s in overviews)
assert sum(len(c['titles']) for c in cards)==len(e['stories'])
with wave.open(str(run/'narration.wav')) as w:
 rate=w.getframerate();pcm=array('h');pcm.frombytes(w.readframes(w.getnframes()))
 if sys.byteorder!='little':pcm.byteswap()
 assert abs(len(pcm)/rate-shots[-1]['end'])<.001
 for g in gaps:assert not any(pcm[round(g['start']*rate):round(g['end']*rate)])
levels=[]
for g in gaps:
 assert abs(g['end']-g['start']-3.4)<.0001
 assert all(s['end']<=g['start']+.0001 or s['start']>=g['end']-.0001 for s in shots)
 r=subprocess.run([FFMPEG,'-v','error','-ss',str(g['start']+.08),'-i',str(run/'news.mp4'),'-t','3.24','-map','0:a:0','-ac','1','-ar','24000','-f','f32le','-'],capture_output=True,check=True)
 a=array('f');a.frombytes(r.stdout)
 if sys.byteorder!='little':a.byteswap()
 db=20*math.log10(max(max(map(abs,a),default=0),1e-12))
 assert db < -60;levels.append(db)
peaks={}
for filename in ['news.mp4','news-no-bgm.mp4']:
 subprocess.run([FFMPEG,'-v','error','-i',str(run/filename),'-f','null','-'],capture_output=True,check=True)
 r=subprocess.run([FFMPEG,'-hide_banner','-i',str(run/filename),'-vn','-af','loudnorm=I=-18:TP=-3:LRA=7:print_format=json','-f','null','-'],capture_output=True,check=True)
 txt=r.stderr.decode('utf8',errors='replace');stats=json.loads(txt[txt.rfind('{'):txt.rfind('}')+1]);peaks[filename]=stats
 assert float(stats['input_tp'])<=-3
write_json(out/'performance-audit.json', performance_audit(plan['shots']))
# Three actual frames per utterance: initial pose, speaking focus/hold, restored pose.
samples=[]
for i,s in enumerate(shots):
 event=s['performance_events'][1]['at'];last=s['performance_events'][2]['at']
 samples.extend([(i,'start',s['start']+.02),(i,'focus',s['start']+min(last-.02,event+.12)),(i,'end',s['end']-.04)])
indices=sorted(set(round(x[2]*30) for x in samples))
select='+'.join(f'eq(n,{n})' for n in indices)
# The appended outro may change H.264 parameters. Keep the sample counter
# continuous when that boundary would otherwise reinitialize the filters.
subprocess.run([FFMPEG,'-v','error','-y','-reinit_filter','0','-i',str(run/'news.mp4'),'-map','0:v:0','-vf',f'select={select.replace(",",chr(92)+",")},scale=640:360','-fps_mode','vfr','-q:v','2',str(out/'frame-%03d.jpg')],capture_output=True,check=True)
frames=sorted(out.glob('frame-*.jpg'));assert len(frames)==len(indices)
font=None
for page in range(math.ceil(len(frames)/12)):
 sheet=Image.new('RGB',(1920,4*386),'white');d=ImageDraw.Draw(sheet)
 for j,frame in enumerate(frames[page*12:(page+1)*12]):
  n=page*12+j;x=j%3*640;y=j//3*386
  with Image.open(frame) as im:sheet.paste(im,(x,y))
  d.text((x+5,y+361),f'frame {indices[n]} / {indices[n]/30:.3f}s',fill='black')
 sheet.save(out/f'contact-{page:02d}.jpg',quality=90)
write_json(out/'programme-qa.json',dict(status='passed',stories=len(e['stories']),cues=len(captions),overview_screens=len(cards),interludes=len(gaps),chapters=len(read_json(run/'chapters.json')['chapters']),duration=build_navigation(e,t)['duration'],video_sha256=sha256(run/'news.mp4'),source_and_output_hashes=True,voice_lineage=True,speech_pose_events=True,subtitles=True,silent_pcm_interludes=True,decoded_interlude_peak_db=levels,decoded_audio=peaks,full_decode_both_versions=True,actual_frames=len(frames),manual_full_listening=False))
print('PASSED: actual delivery lineage, decoded audio, subtitles, navigation and',len(frames),'sample frames',flush=True)
