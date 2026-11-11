import subprocess
import tempfile
import unittest
from pathlib import Path

from pipeline import chapterbar


def fixture():
    return dict(
        duration=2,
        chapters=[
            dict(id="opening", scene=-3, start=0),
            dict(id="overview-headlines", scene=-1, start=0.5),
            dict(id="story", scene=0, start=1),
            dict(id="outro", scene=-2, start=1.5),
        ],
        sections=[dict(id="headlines", title="头条新闻", start=1)],
    )


class ChapterBarTests(unittest.TestCase):
    def test_visible_labels_use_timeline_boundaries(self):
        self.assertEqual(chapterbar.segments(fixture()), [
            (0, "开场"), (0.5, "目录"), (1, "头条新闻"), (1.5, "片尾"),
        ])

    def test_preserves_adjacent_frames_closer_than_nominal_frame_interval(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, output = root / "join.mp4", root / "overlay.mp4"
            ffmpeg = chapterbar.FFMPEG
            subprocess.run([
                ffmpeg, "-v", "error", "-f", "lavfi", "-i", "color=green:s=320x180:r=10:d=2",
                "-vf", "settb=1/1000,setpts='N*100-if(eq(N,10),65,0)'",
                "-fps_mode", "passthrough", "-enc_time_base", "1/1000", "-c:v", "libx264", "-bf", "0",
                "-bsf:v", "setts=duration=100",
                str(source),
            ], check=True)
            chapterbar.overlay(source, output, fixture())
            frames = subprocess.check_output([
                ffmpeg, "-v", "error", "-i", str(output), "-map", "0:v:0", "-c", "copy", "-f", "framehash", "-",
            ], text=True)
            self.assertEqual(sum(not line.startswith("#") for line in frames.splitlines()), 20)

    def test_overlay_keeps_lower_content_and_audio_and_fills_by_time(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, output = root / "base.mp4", root / "overlay.mp4"
            metadata = root / "chapters.txt"
            metadata.write_text(";FFMETADATA1\n[CHAPTER]\nTIMEBASE=1/1000\nSTART=0\nEND=2000\ntitle=Opening\n")
            ffmpeg = chapterbar.FFMPEG
            subprocess.run([
                ffmpeg, "-v", "error", "-f", "lavfi", "-i", "color=green:s=320x180:r=10:d=2",
                "-f", "lavfi", "-i", "sine=frequency=440:duration=2", "-i", str(metadata),
                "-map", "0:v", "-map", "1:a", "-map_chapters", "2",
                "-vf", "drawbox=y=ih-6:h=6:color=white:t=fill", "-c:v", "libx264", "-c:a", "aac",
                str(source),
            ], check=True)
            chapterbar.overlay(source, output, fixture())
            frames = subprocess.check_output([
                ffmpeg, "-v", "error", "-i", str(output), "-f", "rawvideo", "-pix_fmt", "rgb24", "-",
            ])
            frame_size = 320 * 180 * 3
            self.assertEqual(len(frames), frame_size * 20)

            def pixel(frame, x, y):
                start = frame_size * frame + (320 * y + x) * 3
                return frames[start:start + 3]

            self.assertGreater(min(pixel(0, 160, 165)), 200)
            self.assertLess(pixel(0, 25, 178)[0], 70)
            self.assertGreater(pixel(10, 25, 178)[0], 175)
            self.assertLess(pixel(10, 305, 178)[0], 70)
            self.assertGreater(pixel(19, 315, 178)[0], 175)
            for path in (source, output):
                chapters = subprocess.check_output([
                    ffmpeg, "-v", "error", "-i", str(path), "-f", "ffmetadata", "-",
                ])
                self.assertIn(b"title=Opening", chapters)
            audio = lambda path: subprocess.check_output([
                ffmpeg, "-v", "error", "-i", str(path), "-map", "0:a:0", "-c", "copy", "-f", "data", "-",
            ])
            self.assertEqual(audio(source), audio(output))
