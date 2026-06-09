from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path


WIDTH = 1080
HEIGHT = 1920
FPS = 30
DEFAULT_DURATION_SECONDS = 25
PREVIEW_DURATION_SECONDS = 12
PREVIEW_WIDTH = 540
PREVIEW_HEIGHT = 960


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def render_video_package(
    video_dir: Path,
    duration_seconds: int = DEFAULT_DURATION_SECONDS,
    preview: bool = False,
) -> dict:
    video_dir = video_dir.resolve()
    if not ffmpeg_available():
        return {
            "video_dir": str(video_dir),
            "rendered": False,
            "output": None,
            "warning": "FFmpeg not found. Keeping script, subtitles, and metadata files only.",
        }

    plan_path = video_dir / "video-plan.json"
    subtitles_path = video_dir / "subtitles.srt"
    voiceover_path = video_dir / "voiceover.mp3"
    output_path = video_dir / ("preview.mp4" if preview else "final.mp4")
    thumbnail_path = video_dir / ("preview-thumbnail.jpg" if preview else "thumbnail.jpg")
    width = PREVIEW_WIDTH if preview else WIDTH
    height = PREVIEW_HEIGHT if preview else HEIGHT

    if not plan_path.exists():
        return _failed(video_dir, "video-plan.json not found")

    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    title = clean_title(plan)
    category = plan.get("trend", {}).get("category", "Trend")
    subtitle_text = clean_subtitle_text(plan, duration_seconds)

    with tempfile.TemporaryDirectory() as temp_dir:
        title_path = Path(temp_dir) / "title.txt"
        render_subtitles_path = Path(temp_dir) / "render-subtitles.srt"
        title_path.write_text(_wrap_text(title, 24, max_lines=2), encoding="utf-8")
        render_subtitles_path.write_text(make_render_subtitles(subtitle_text, duration_seconds), encoding="utf-8")

        filtergraph = ",".join(
            [
                "format=yuv420p",
                _draw_background_overlay(category, width, height),
                _draw_title_filter(title_path, preview=preview),
                _draw_brand_filter(preview=preview),
                _subtitles_filter(render_subtitles_path, preview=preview),
            ]
        )

        command = [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c={_background_color(category)}:s={width}x{height}:r={FPS}:d={duration_seconds}",
        ]
        if voiceover_path.exists():
            command.extend(["-i", str(voiceover_path), "-shortest"])

        command.extend(
            [
                "-vf",
                filtergraph,
                "-t",
                str(duration_seconds),
                "-map",
                "0:v:0",
            ]
        )
        if voiceover_path.exists():
            command.extend(["-map", "1:a:0", "-c:a", "aac", "-b:a", "160k"])

        command.extend(
            [
                "-c:v",
                "libx264",
                "-preset",
                "ultrafast" if preview else "medium",
                "-crf",
                "28" if preview else "23",
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
                str(output_path),
            ]
        )

        completed = subprocess.run(command, capture_output=True, text=True, timeout=180)

    if completed.returncode != 0:
        return {
            "video_dir": str(video_dir),
            "rendered": False,
            "output": None,
            "warning": "FFmpeg render failed.",
            "stderr": completed.stderr[-2000:],
        }

    thumbnail_result = _create_thumbnail(output_path, thumbnail_path)

    return {
        "video_dir": str(video_dir),
        "rendered": True,
        "output": str(output_path),
        "thumbnail": str(thumbnail_path) if thumbnail_path.exists() else None,
        "thumbnail_warning": thumbnail_result.get("warning"),
        "audio_used": voiceover_path.exists(),
        "preview": preview,
        "warning": None if voiceover_path.exists() else "Rendered silent video: voiceover.mp3 not found.",
    }


def render_all(video_root: Path, duration_seconds: int = DEFAULT_DURATION_SECONDS, preview: bool = False) -> dict:
    video_dirs = [
        path
        for path in sorted(video_root.iterdir())
        if path.is_dir() and (path / "video-plan.json").exists()
    ]
    return render_video_dirs(video_dirs, duration_seconds=duration_seconds, preview=preview)


def render_video_dirs(
    video_dirs: list[Path],
    duration_seconds: int = DEFAULT_DURATION_SECONDS,
    preview: bool = False,
) -> dict:
    results = [render_video_package(path, duration_seconds=duration_seconds, preview=preview) for path in video_dirs]
    return {
        "ffmpeg_available": ffmpeg_available(),
        "attempted": len(video_dirs),
        "rendered_count": sum(1 for result in results if result["rendered"]),
        "outputs": [result["output"] for result in results if result["output"]],
        "thumbnails": [result["thumbnail"] for result in results if result.get("thumbnail")],
        "warnings": [result["warning"] for result in results if result.get("warning")],
        "preview": preview,
        "duration_seconds": duration_seconds,
        "results": results,
    }


def _failed(video_dir: Path, warning: str) -> dict:
    return {
        "video_dir": str(video_dir),
        "rendered": False,
        "output": None,
        "warning": warning,
    }


def _background_color(category: str) -> str:
    colors = {
        "Sports": "0x17324D",
        "Horror Stories": "0x171117",
        "Funny Kids": "0x245C7A",
        "Viral News": "0x23303A",
        "Gaming": "0x1D214F",
        "AI": "0x102A3A",
        "Celebrity": "0x3A2038",
        "Animals": "0x1F3D2B",
        "Movies & TV": "0x28233A",
        "Misc Viral": "0x263238",
    }
    return colors.get(category, colors["Misc Viral"])


def _draw_background_overlay(category: str, width: int, height: int) -> str:
    accent = {
        "Sports": "0x32D583",
        "Horror Stories": "0xD92D20",
        "Funny Kids": "0xFDB022",
        "Viral News": "0x53B1FD",
        "Gaming": "0x9B8AFB",
        "AI": "0x2ED3B7",
        "Celebrity": "0xEE46BC",
        "Animals": "0x86CB3C",
        "Movies & TV": "0xF97066",
        "Misc Viral": "0xA6F4C5",
    }.get(category, "0xA6F4C5")
    return (
        f"drawbox=x=0:y=0:w={width}:h={int(height * 0.18)}:color={accent}@0.12:t=fill,"
        f"drawbox=x={int(width * 0.08)}:y={int(height * 0.18)}:w={int(width * 0.84)}:h=4:color={accent}@0.7:t=fill,"
        f"drawbox=x={int(width * 0.08)}:y={int(height * 0.72)}:w={int(width * 0.84)}:h={int(height * 0.18)}:color=black@0.22:t=fill"
    )


def _draw_title_filter(title_path: Path, preview: bool = False) -> str:
    fontsize = 28 if preview else 46
    x = 42 if preview else 82
    y = 112 if preview else 215
    boxborderw = 14 if preview else 22
    return (
        "drawtext="
        f"fontfile='{_ffmpeg_path(_font_path())}':"
        f"textfile='{_ffmpeg_path(title_path)}':"
        "fontcolor=white:"
        f"fontsize={fontsize}:"
        f"line_spacing={8 if preview else 14}:"
        f"x={x}:"
        f"y={y}:"
        "box=1:"
        "boxcolor=black@0.36:"
        f"boxborderw={boxborderw}"
    )


def _draw_brand_filter(preview: bool = False) -> str:
    return (
        "drawtext="
        f"fontfile='{_ffmpeg_path(_font_path())}':"
        "text='Masyra Labs':"
        "fontcolor=white@0.92:"
        f"fontsize={20 if preview else 34}:"
        f"x={42 if preview else 82}:"
        f"y={42 if preview else 78}:"
        "box=1:"
        "boxcolor=black@0.22:"
        f"boxborderw={8 if preview else 14}"
    )


def _subtitles_filter(subtitles_path: Path, preview: bool = False) -> str:
    fontsize = 13 if preview else 16
    margin_v = 84 if preview else 170
    return (
        "subtitles="
        f"filename='{_ffmpeg_path(subtitles_path)}':"
        f"force_style='FontName=Arial,FontSize={fontsize},PrimaryColour=&H00FFFFFF,"
        "OutlineColour=&HAA000000,BorderStyle=3,Outline=1,Shadow=0,"
        f"Alignment=2,MarginV={margin_v}'"
    )


def _font_path() -> Path:
    windows_font = Path("C:/Windows/Fonts/arial.ttf")
    if windows_font.exists():
        return windows_font
    return Path("Arial")


def _ffmpeg_path(path: Path) -> str:
    return str(path).replace("\\", "/").replace(":", "\\:")


def _wrap_text(text: str, max_chars: int, max_lines: int = 2) -> str:
    words = text.replace("#shorts", "").split()
    lines: list[str] = []
    current: list[str] = []
    for word in words:
        candidate = " ".join([*current, word])
        if len(candidate) > max_chars and current:
            lines.append(" ".join(current))
            current = [word]
        else:
            current.append(word)
    if current:
        lines.append(" ".join(current))
    return "\n".join(lines[:max_lines])


def _create_thumbnail(video_path: Path, thumbnail_path: Path) -> dict:
    command = [
        "ffmpeg",
        "-y",
        "-ss",
        "00:00:02",
        "-i",
        str(video_path),
        "-frames:v",
        "1",
        "-q:v",
        "3",
        str(thumbnail_path),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, timeout=60)
    if completed.returncode != 0:
        return {"created": False, "warning": completed.stderr[-1000:]}
    return {"created": True, "warning": None}


def clean_title(plan: dict) -> str:
    raw = plan.get("trend", {}).get("title") or plan.get("title") or "Masyra Labs Trend"
    raw = raw.replace("#shorts", "")
    raw = re.sub(r"^(This .*?:|Sports Fans Are Talking About This:|Gamers Are Sharing This:)\s*", "", raw).strip()
    return raw[:72].rstrip(" -:")


def clean_subtitle_text(plan: dict, duration_seconds: int) -> str:
    narration = plan.get("narration", "")
    title = plan.get("trend", {}).get("title", "")
    if title:
        narration = narration.replace(title, "").replace("  ", " ")
    narration = re.sub(r"^This [^.]+ trend is moving fast:\s*\.?\s*", "", narration, flags=re.IGNORECASE)
    narration = narration.strip()
    if not narration:
        narration = "A quick original Masyra Labs breakdown of why this trend is moving."
    words = narration.split()
    max_words = 38 if duration_seconds <= PREVIEW_DURATION_SECONDS else 70
    return " ".join(words[:max_words])


def make_render_subtitles(text: str, duration_seconds: int) -> str:
    words = text.split()
    if not words:
        return ""
    chunk_size = 7
    chunks = [" ".join(words[index:index + chunk_size]) for index in range(0, len(words), chunk_size)]
    max_chunks = 3 if duration_seconds <= PREVIEW_DURATION_SECONDS else 5
    chunks = chunks[:max_chunks]
    start = max(2, int(duration_seconds * 0.42))
    available = max(duration_seconds - start - 1, len(chunks) * 2)
    block_duration = max(2, available // max(len(chunks), 1))
    blocks = []
    current = start
    for index, chunk in enumerate(chunks, start=1):
        end = min(duration_seconds - 1, current + block_duration)
        blocks.append(f"{index}\n{_srt_time(current)} --> {_srt_time(end)}\n{chunk}\n")
        current = end
    return "\n".join(blocks)


def _srt_time(seconds: int) -> str:
    return f"00:00:{seconds:02d},000"
