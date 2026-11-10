import unittest
from PIL import Image, ImageChops
from pipeline import render


class VoiceEffectsTests(unittest.TestCase):
    def test_export_effects_move_only_during_speech_and_repeat_exactly(self):
        gate = 'gte(t,0.2)*lt(t,0.7)'
        x, y = render.voice_jitter(gate)
        graph = f"[0:v][1:v]overlay=x='70+({x})':y='40+({y})':eval=frame[host];"
        graph += render.voice_particles('host', (40, 15, 80, 90), gate, 30)
        args = [render.FFMPEG, '-v', 'error', '-f', 'lavfi', '-i',
                'color=black:s=160x120:r=30', '-f', 'lavfi', '-i',
                'color=white:s=12x32:r=30', '-filter_complex', graph,
                '-map', '[voicefx]', '-t', '1', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-']
        raw = render.command(args).stdout
        self.assertEqual(raw, render.command(args).stdout)
        size = 160 * 120 * 3
        frames = [Image.frombytes('RGB', (160, 120), raw[i:i+size])
                  for i in range(0, len(raw), size)]
        def yellow(frame):
            return sum(r > 120 and g > 120 and b < 180 and g > b*1.2
                       for r, g, b in frame.getdata())
        self.assertEqual(yellow(frames[0]), 0)
        self.assertGreater(yellow(frames[10]), 0)
        self.assertEqual(yellow(frames[27]), 0)
        self.assertIsNone(ImageChops.difference(frames[0], frames[27]).getbbox())
        self.assertIsNotNone(ImageChops.difference(frames[10], frames[13]).getbbox())
        def host_box(frame):
            return frame.point(lambda v: 255 if v > 245 else 0).convert('L').point(
                lambda v: 255 if v > 245 else 0).getbbox()
        self.assertNotEqual(host_box(frames[10]), host_box(frames[13]))


if __name__ == '__main__':
    unittest.main()
