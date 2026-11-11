"""Burn a section-level ChapterBar into an assembled news video."""
import argparse
import json
import math
import os
import subprocess
import tempfile
from pathlib import Path

import imageio_ffmpeg
from PIL import Image, ImageDraw, ImageFont

from .core import read_json, sha256


FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
BACKGROUND = "202124"
FILL = "FF9F1A"
SHORT_TITLES = {"github": "开源项目"}


def segments(navigation):
    duration = navigation["duration"]
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("章节进度条需要有效的视频时长")

    result = [(0, "开场")]
    overview = next((entry for entry in navigation["chapters"] if entry["id"].startswith("overview-")), None)
    if overview is not None:
        result.append((overview["start"], "目录"))
    for section in navigation["sections"]:
        result.append((section["start"], SHORT_TITLES.get(section["id"], section["title"])))
    outro = next((entry for entry in navigation["chapters"] if entry["id"] == "outro"), None)
    if outro is not None:
        result.append((outro["start"], "片尾"))

    # An older issue can start directly with an overview or news section.
    if len(result) > 1 and result[1][0] == 0:
        result.pop(0)
    previous = -1
    for start, title in result:
        if not previous < start < duration or not title.strip():
            raise ValueError("章节进度条分段时间必须严格递增，标题不能为空")
        previous = start
    return result


def load_font(path, size):
    if path:
        return ImageFont.truetype(str(path), size)
    windows_fonts = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
    candidates = (
        windows_fonts / "msyh.ttc",
        windows_fonts / "simhei.ttf",
        windows_fonts / "simsun.ttc",
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/Supplemental/Songti.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    )
    for candidate in candidates:
        if Path(candidate).is_file():
            return ImageFont.truetype(str(candidate), size)
    raise ValueError("找不到中文字体，请用 --font 指定 TTF、OTF 或 TTC 字体")


# Label fitting adapted from ChapterBar (MIT), see docs/licenses/ChapterBar-MIT.txt.
def fit_label(draw, label, font, width):
    if draw.textlength(label, font=font) <= width:
        return label
    ellipsis = "…"
    if draw.textlength(ellipsis, font=font) > width:
        return ""
    low, high = 0, len(label)
    while low < high:
        mid = (low + high + 1) // 2
        if draw.textlength(label[:mid] + ellipsis, font=font) <= width:
            low = mid
        else:
            high = mid - 1
    return label[:low] + ellipsis if low else ""


def draw_labels(labels, duration, width, height, font_path, output):
    image = Image.new("RGBA", (width, height))
    draw = ImageDraw.Draw(image)
    font = load_font(font_path, max(9, round(height * 0.57)))
    edges = [round(start * width / duration) for start, _ in labels] + [width]
    padding = max(3, height // 7)
    for (_, title), left, right in zip(labels, edges, edges[1:]):
        if 0 < left < width:
            draw.line((left, padding, left, height - padding - 1), fill="#B1B5BB", width=max(1, height // 19))
        label = fit_label(draw, title, font, right - left - 2 * padding)
        if label:
            draw.text(((left + right) / 2, height / 2), label, font=font, anchor="mm",
                      fill="white", stroke_width=int(height >= 24), stroke_fill="#292825")
    image.save(output)


def overlay(source, output, navigation, font=None):
    source, output = Path(source), Path(output)
    if source.suffix.lower() != ".mp4" or output.suffix.lower() != ".mp4":
        raise ValueError("章节进度条需要 MP4 输入和输出")
    if output.exists() or source.resolve() == output.resolve():
        raise FileExistsError(output)
    labels = segments(navigation)
    duration = navigation["duration"]
    reader = imageio_ffmpeg.read_frames(str(source))
    try:
        metadata = next(reader)
    finally:
        reader.close()
    width, height = metadata["size"]
    fps = metadata["fps"]
    if not fps or min(width, height) < 64 or width % 2 or height % 2:
        raise ValueError("章节进度条需要有效帧率以及不小于 64×64 的偶数尺寸视频")
    if abs(metadata["duration"] - duration) > max(0.1, 2 / fps):
        raise ValueError("章节时间线与视频时长不一致")
    bar = max(12, 2 * round(height * 0.036 / 2))
    last_frame = max(1, round(duration * fps) - 1)
    with tempfile.TemporaryDirectory(prefix=".chapterbar-", dir=output.parent) as tmp:
        plate, temporary = Path(tmp) / "labels.png", Path(tmp) / "video.mp4"
        draw_labels(labels, duration, width, bar, font, plate)
        # Fit the existing picture above the rail, preserving proportions and all pixels.
        graph = (
            f"[0:v]scale={width}:{height-bar}:force_original_aspect_ratio=decrease:force_divisible_by=2,"
            f"pad={width}:{height}:(ow-iw)/2:0:color=0x{BACKGROUND},setsar=1[base];"
            f"color=c=0x{FILL}:s={width}x{bar}:r=1:d=1[paint];"
            f"[base][paint]overlay=x='-w+2*floor(w*clip((n-1)/{last_frame},0,1)/2)':y=H-h[filled];"
            "[filled][1:v]overlay=0:H-h,format=yuv420p[out]"
        )
        command = [
            FFMPEG, "-hide_banner", "-v", "error", "-xerror", "-reinit_filter", "0", "-i", str(source),
            "-i", str(plate), "-filter_complex_threads", "1", "-filter_complex", graph,
            "-map", "[out]", "-map", "0:a?", "-map_metadata", "0", "-map_chapters", "0",
            "-fps_mode", "passthrough", "-enc_time_base:v", "demux",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "19", "-threads", "4",
            "-c:a", "copy", "-movflags", "+faststart", str(temporary),
        ]
        result = subprocess.run(command, capture_output=True)
        if result.returncode:
            raise ValueError("章节进度条合成失败: " + result.stderr.decode("utf-8", errors="replace").strip())
        # Publish only the finished file and never replace an existing version.
        if os.name == "nt":
            temporary.rename(output)
        else:
            os.link(temporary, output)
    return dict(
        source_sha256=sha256(source), sha256=sha256(output), width=width, height=height,
        bar_height=bar, duration=duration, fps=fps, timing_basis="final_measured_shot_timeline",
        segments=[dict(start=start, title=title) for start, title in labels],
    )


def main():
    parser = argparse.ArgumentParser(description="为已有新闻 MP4 加入章节进度条，保留原视频和音轨")
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--chapters", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--font", type=Path, help="可选中文字体路径")
    args = parser.parse_args()
    try:
        receipt = overlay(args.video, args.output, read_json(args.chapters), font=args.font)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(2, f"chapterbar: {exc}\n")
    print(json.dumps(receipt, ensure_ascii=False))


if __name__ == "__main__":
    main()
