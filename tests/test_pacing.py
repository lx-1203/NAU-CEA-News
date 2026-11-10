import math
import struct
import tempfile
import unittest
import wave
from pathlib import Path

from pipeline.pacing import spoken_units, target_cpm, pace_wav


def tone(path, seconds=2.5, frequency=440):
    rate=24000
    samples=[0]*9600+[round(9000*math.sin(2*math.pi*frequency*i/rate)) for i in range(round(seconds*rate))]+[0]*9600
    with wave.open(str(path),'wb') as w:
        w.setparams((1,2,rate,0,'NONE','not compressed'))
        w.writeframes(struct.pack('<'+'h'*len(samples),*samples))


class PacingTests(unittest.TestCase):
    def test_counts_actual_number_readings_and_circle_zero(self):
        self.assertEqual(spoken_units('目标2028年末发射。'),len('目标二〇二八年末发射'))
        self.assertEqual(spoken_units('比例30%。'),len('比例百分之三十'))
        self.assertEqual(spoken_units('AI与CPU'),6)
        self.assertEqual(spoken_units('二〇二八'),4)
        self.assertEqual(spoken_units('共10,000台。'),len('共一万台'))

    def test_unknown_english_name_needs_spoken_override(self):
        with self.assertRaises(ValueError): spoken_units('Repomix发布更新。')
        self.assertEqual(spoken_units('Repomix发布更新。','瑞破米克斯发布更新'),9)
        with self.assertRaises(ValueError):spoken_units('未来1–2个月。')

    def test_numbers_and_technical_terms_get_slower_target(self):
        policy={'normal_cpm':295,'sensitive_cpm':285,'terms':['核动力','专家缓存']}
        self.assertEqual(target_cpm('目标二〇二八年发射。',policy),285)
        self.assertEqual(target_cpm('其中包括核动力月球车。',policy),285)
        self.assertEqual(target_cpm('计划十八个月。',policy,sensitive=False),285)
        self.assertEqual(target_cpm('欢迎关注校园生活。',policy),295)

    def test_real_audio_hits_target_including_video_gap_and_preserves_pitch(self):
        from pipeline.core import sha256
        import numpy as np
        with tempfile.TemporaryDirectory() as d:
            src=Path(d)/'source.wav';out=Path(d)/'paced.wav';tone(src)
            digest=sha256(src)
            row=pace_wav(src,out,'这是一个语速测试示例。',{},extra_gap=.22)
            self.assertEqual(digest,sha256(src))
            self.assertTrue(280<=row['effective_cpm']<=300)
            with wave.open(str(out)) as w:
                signal=np.frombuffer(w.readframes(w.getnframes()),dtype='<i2').astype(float);rate=w.getframerate()
            window=signal[len(signal)//3:len(signal)*2//3]
            freq=np.fft.rfftfreq(len(window),1/rate)[np.argmax(abs(np.fft.rfft(window)))]
            self.assertLess(abs(freq-440),5)

    def test_silence_and_unsafe_acceleration_fail_without_overwriting_source(self):
        with tempfile.TemporaryDirectory() as d:
            src=Path(d)/'source.wav';out=Path(d)/'paced.wav'
            with wave.open(str(src),'wb') as w:
                w.setparams((1,2,24000,0,'NONE','not compressed'));w.writeframes(b'\0\0'*24000)
            with self.assertRaises(ValueError): pace_wav(src,out,'测试。',{})
            tone(src,seconds=7)
            with self.assertRaises(ValueError): pace_wav(src,out,'测试。',{})
            self.assertFalse(out.exists())

    def test_slow_take_can_use_lower_target_inside_band_without_exceeding_tempo_limit(self):
        with tempfile.TemporaryDirectory() as d:
            src=Path(d)/'source.wav';out=Path(d)/'paced.wav';tone(src,seconds=2.7)
            row=pace_wav(src,out,'欢迎收看今天校园新闻。',{})
            self.assertLess(row['target_cpm'],295)
            self.assertLessEqual(row['tempo'],1.60)
            self.assertTrue(280<=row['effective_cpm']<=300)

    def test_disabled_pacing_does_not_touch_existing_audio(self):
        from pipeline.pacing import pace_for_render
        with tempfile.TemporaryDirectory() as d:
            src=Path(d)/'source.wav';tone(src);before=src.read_bytes()
            self.assertIsNone(pace_for_render(src,{'text':'测试。'},{'enabled':False}))
            self.assertEqual(before,src.read_bytes())
            self.assertEqual(len(list(Path(d).iterdir())),1)

    def test_summary_rejects_missing_or_out_of_range_receipts(self):
        from pipeline.pacing import pacing_summary
        for rows in [[],[dict(scene=0,anchor='xiaoXu',duration=2)],[dict(scene=0,anchor='xiaoXu',duration=4,pacing={'spoken_units':10})]]:
            with self.subTest(rows=rows),self.assertRaises(ValueError):pacing_summary(rows,{})

    def test_pronunciation_annotation_preserves_script_and_anchor(self):
        from pipeline.workbench import edition_lines
        e={'date':'2026-11-09','stories':[{'narration':['更新Repomix。']}],
           'speech_annotations':{'3':{'spoken_text':'更新瑞破米克斯','sensitive':True,'text':'不可替换稿件'}}}
        line=edition_lines(e)[3]
        self.assertEqual(line['text'],'更新Repomix。')
        self.assertEqual(line['anchor'],'xiaoXu')
        self.assertEqual(line['spoken_text'],'更新瑞破米克斯')


if __name__=='__main__': unittest.main()
