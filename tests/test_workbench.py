import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch, Mock

from pipeline.core import sha256


class WorkbenchTests(unittest.TestCase):
    def test_cuda_cold_failure_retries_once_with_fingerprint_resume(self):
        from pipeline.workbench import run_workbench_batch
        import subprocess
        with tempfile.TemporaryDirectory() as temp:
            run=Path(temp);session=Mock();session.get.return_value.json.return_value={'generating':False,'loaded':True}
            calls=[]
            def execute(args,**kw):
                calls.append(args)
                if len(calls)==1:
                    kw['stderr'].write(b'CUDA out of memory');kw['stdout'].write(b'{"ok":false}')
                    return subprocess.CompletedProcess(args,1)
                kw['stdout'].write(b'{"ok":true}')
                return subprocess.CompletedProcess(args,0)
            with patch('pipeline.workbench.subprocess.run',side_effect=execute):
                run_workbench_batch(['python','client.py','batch'],{'INDEXTTS_URL':'http://127.0.0.1:7861'},run,session)
            self.assertEqual(len(calls),2);self.assertIn('--resume',calls[-1])
            self.assertIn('CUDA out of memory',(run/'workbench-progress-attempt1.log').read_text())
            self.assertTrue((run/'workbench-warm-retry.json').is_file())

    def test_background_workbench_start_uses_files_and_low_memory_environment(self):
        from pipeline.workbench import start_workbench
        import subprocess
        with tempfile.TemporaryDirectory() as temp:
            run=Path(temp)
            cfg={'speech_shell':'pwsh'};wb={'start_script':'start.ps1','low_memory_load':True}
            with patch('pipeline.workbench.subprocess.run',return_value=subprocess.CompletedProcess([],0)) as call:
                start_workbench(cfg,wb,run)
            kw=call.call_args.kwargs
            self.assertNotIn('capture_output',kw)
            self.assertEqual(kw['env']['INDEXTTS_LOW_MEMORY_LOAD'],'1')
            self.assertNotEqual(kw['stdout'],subprocess.PIPE)
            self.assertTrue((run/'workbench-start.log').exists())

    def test_optional_opening_briefs_keep_original_studio_and_three_headlines(self):
        from pipeline.workbench import edition_lines
        edition={'date':'2026-11-09','stories':[{'narration':['新闻正文。']}],
                 'opening_briefs':['先看机器人新进展。','再看航天任务。','还有一项临床研究。']}
        lines=edition_lines(edition)
        self.assertEqual(lines[0]['text'],'这里是南京农业大学计算机爱好者协会。')
        self.assertEqual(lines[1]['text'],'欢迎收看NJAU-CEA新闻联播。')
        self.assertEqual([x['text'] for x in lines[3:6]],edition['opening_briefs'])
        self.assertTrue(all(x['scene']==-1 for x in lines[:6]))
        self.assertEqual(lines[6]['text'],'新闻正文。')
        for bad in ['不能用字符串冒充列表。',['甲。']*4,['超'*23]]:
            with self.assertRaises(ValueError):edition_lines(dict(edition,opening_briefs=bad))

    def test_full_scale_workbench_audio_keeps_three_db_export_headroom(self):
        import subprocess,re
        from pipeline.render import FFMPEG, PAD_AUDIO_FILTER, normalize_speech
        with tempfile.TemporaryDirectory() as temp:
            wav=Path(temp)/'speech.wav'
            subprocess.run([FFMPEG,'-v','error','-f','lavfi','-i',
                            'aevalsrc=0.999*sin(2*PI*440*t):s=24000:d=0.8',str(wav)],capture_output=True,check=True)
            stats=normalize_speech(wav)
            self.assertTrue(stats['gain_db'] < 0)
            result=subprocess.run([FFMPEG,'-hide_banner','-i',str(wav),
                                   '-af',PAD_AUDIO_FILTER+',volumedetect','-t','1','-f','null','-'],capture_output=True,check=True)
        peak=float(re.search(r'max_volume: ([-\w.]+) dB',result.stderr.decode()).group(1))
        self.assertLessEqual(peak,-2.9)

    def test_twenty_db_input_difference_is_balanced_without_changing_duration(self):
        import subprocess,math,array
        from pipeline.render import FFMPEG,normalize_speech
        levels=[]
        with tempfile.TemporaryDirectory() as temp:
            for i,amp in enumerate([.8,.08]):
                wav=Path(temp)/f'speech{i}.wav'
                subprocess.run([FFMPEG,'-v','error','-f','lavfi','-i',
                                f'aevalsrc={amp}*sin(2*PI*440*t):s=24000:d=1',str(wav)],capture_output=True,check=True)
                normalize_speech(wav)
                with wave.open(str(wav)) as w:
                    self.assertEqual(w.getnframes(),24000)
                    samples=array.array('h',w.readframes(w.getnframes()))
                levels.append(20*math.log10(math.sqrt(sum(v*v for v in samples)/len(samples))/32768))
        self.assertLess(abs(levels[0]-levels[1]),.5)

    def test_online_workbench_uses_one_batch_without_starting_another_service(self):
        from pipeline.workbench import prepare_workbench_audio
        from pipeline.core import write_json
        import subprocess
        import json
        with tempfile.TemporaryDirectory() as temp:
            base=Path(temp); run=base/'run'; run.mkdir()
            ref=base/'ref.wav'; ref.write_bytes(b'fixed reference')
            (base/'client.py').write_text('# test client',encoding='utf8')
            state=base/'state.json'; write_json(state, {'url':'http://127.0.0.1:7891'})
            voice=dict(name='小序', reference=str(ref), sha256=sha256(ref))
            wb=dict(state_file=str(state), project_dir=str(base), client_config_dir=str(base),
                    output_root=str(base/'cache'), client=str(base/'client.py'), start_script='must-not-start.ps1',
                    voices={'xiaoXu':voice}, parameters={})
            lines=[dict(text='当天新闻。', anchor='xiaoXu')]
            session=Mock();session.get.return_value.json.side_effect=[{'status':'ok'},{'generating':False}]
            calls=[]
            def execute(args, **kwargs):
                calls.append(args)
                if 'segments' in args: return subprocess.CompletedProcess(args,0,b'{"ok":true}',b'')
                tasks=json.loads((run/'workbench-tasks.json').read_text(encoding='utf8'))['items']
                items=[]
                for task in tasks:
                    audio=Path(task['out'])
                    with wave.open(str(audio),'wb') as w:
                        w.setparams((1,2,22050,0,'NONE','not compressed'));w.writeframes(b'\0\0'*22050)
                    items.append(dict(id=task['id'],ok=True,out=str(audio),duration=1,mel_capped=False))
                kwargs['stdout'].write(json.dumps(dict(ok=True,items=items)).encode())
                return subprocess.CompletedProcess(args,0)
            with patch('pipeline.workbench.requests.Session',return_value=session), patch('pipeline.workbench.subprocess.run',side_effect=execute):
                entries=prepare_workbench_audio(lines,dict(speech={'workbench':wb},speech_shell='pwsh'),run,'2026-11-08')
            self.assertEqual(len(entries),1)
            self.assertEqual(sum('batch' in c for c in calls),1)
            self.assertFalse(any('must-not-start.ps1' in c for c in calls))
            self.assertTrue((run/'audio-manifest.json').is_file())

    def test_batch_accepts_all_sentences_and_freezes_audio_hash(self):
        from pipeline.workbench import validate_batch
        with tempfile.TemporaryDirectory() as temp:
            audio = Path(temp)/'one.wav'
            with wave.open(str(audio), 'wb') as w:
                w.setparams((1, 2, 22050, 0, 'NONE', 'not compressed'))
                w.writeframes(b'\0\0'*22050)
            lines = [dict(text='测试新闻。', anchor='xiaoXu')]
            result = dict(ok=True, count=1, items=[dict(id='cue-000', ok=True, out=str(audio), duration=1, mel_capped=False)])
            entries = validate_batch(lines, result, {'xiaoXu': {'name': '小序'}})
            self.assertEqual(entries['0']['sha256'], sha256(audio))
            self.assertEqual(entries['0']['text'], '测试新闻。')
            self.assertIn('IndexTTS2', entries['0']['voice'])

    def test_missing_duplicate_failed_or_truncated_never_falls_back(self):
        from pipeline.workbench import validate_batch
        lines = [dict(text='测试新闻。', anchor='xiaoXu')]
        item = dict(id='cue-000', ok=True, out='unused.wav', duration=1)
        for items in [[], [item, item], [dict(item, mel_capped=True)], [dict(item, ok=False)]]:
            with self.subTest(items=items), self.assertRaises(ValueError):
                validate_batch(lines, dict(ok=True, items=items), {'xiaoXu': {'name': '小序'}})

    def test_external_manifest_requires_exact_full_text_and_hash(self):
        from pipeline.workbench import validate_audio_entries
        lines = [dict(text='当天新闻。', anchor='xiaoXu')]
        with tempfile.TemporaryDirectory() as temp:
            audio = Path(temp)/'a.wav'; audio.write_bytes(b'original')
            entry = dict(text='当天新闻。', path=str(audio), sha256=sha256(audio), voice='IndexTTS2 / 小序')
            validate_audio_entries(lines, {'0': entry}, Path(temp))
            for entries in [{}, {'0': dict(entry, text='旧稿。')}, {'0': dict(entry, sha256='bad')}]:
                with self.assertRaises(ValueError): validate_audio_entries(lines, entries, Path(temp))

    def test_renderer_and_workbench_share_exact_line_order(self):
        from pipeline.workbench import edition_lines
        edition = {'date': '2026-11-08', 'stories': [{'narration': ['甲。']}, {'narration': ['乙。']}]}
        lines = edition_lines(edition)
        self.assertEqual(len(lines), 7)
        self.assertEqual([x['anchor'] for x in lines], ['xiaoXu','xiaoXu','xiaoHe','xiaoXu','xiaoHe','xiaoXu','xiaoHe'])
        self.assertEqual([x['text'] for x in lines[3:5]], ['甲。', '乙。'])


if __name__ == '__main__': unittest.main()
