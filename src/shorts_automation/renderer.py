from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path


WIDTH = 1080
HEIGHT = 1920
FPS = 30
DEFAULT_DURATION_SECONDS = 25
PREVIEW_DURATION_SECONDS = 15
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
    if not subtitles_path.exists():
        return _failed(video_dir, "subtitles.srt not found")

    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    title = plan.get("title", "Masyra Labs Trend")
    category = plan.get("trend", {}).get("category", "Trend")

    with tempfile.TemporaryDirectory() as temp_dir:
        title_path = Path(temp_dir) / "title.txt"
        title_path.write_text(_wrap_text(title, 26), encoding="utf-8")

        filtergraph = ",".join(
            [
                "format=yuv420p",
                _draw_background_overlay(category, width, height),
                _draw_title_filter(title_path, preview=preview),
                _draw_brand_filter(preview=preview),
                _subtitles_filter(subtitles_path),
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
        "warning": None,
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
        f"drawbox=x=0:y=0:w={width}:h={int(height * 0.135)}:color={accent}@0.18:t=fill,"
        f"drawbox=x={int(width * 0.065)}:y={int(height * 0.177)}:w={int(width * 0.87)}:h=6:color={accent}@0.75:t=fill,"
        f"drawbox=x={int(width * 0.065)}:y={int(height * 0.786)}:w={int(width * 0.87)}:h=3:color=white@0.24:t=fill"
    )


def _draw_title_filter(title_path: Path, preview: bool = False) -> str:
    fontsize = 36 if preview else 62
    x = 36 if preview else 70
    y = 205 if preview else 410
    boxborderw = 18 if preview else 28
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
        f"fontsize={26 if preview else 44}:"
        f"x={36 if preview else 70}:"
        f"y={58 if preview else 116}:"
        "box=1:"
        "boxcolor=black@0.22:"
        f"boxborderw={10 if preview else 18}"
    )


def _subtitles_filter(subtitles_path: Path) -> str:
    return (
        "subtitles="
        f"filename='{_ffmpeg_path(subtitles_path)}':"
        "force_style='FontName=Arial,FontSize=18,PrimaryColour=&H00FFFFFF,"
        "OutlineColour=&HAA000000,BorderStyle=3,Outline=1,Shadow=0,"
        "Alignment=2,MarginV=190'"
    )


def _font_path() -> Path:
    windows_font = Path("C:/Windows/Fonts/arial.ttf")
    if windows_font.exists():
        return windows_font
    return Path("Arial")


def _ffmpeg_path(path: Path) -> str:
    return str(path).replace("\\", "/").replace(":", "\\:")


def _wrap_text(text: str, max_chars: int) -> str:
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
    return "\n".join(lines[:7])


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
