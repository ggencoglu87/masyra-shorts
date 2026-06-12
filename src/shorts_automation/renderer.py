from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from .ai_video import ai_scene_videos_available, load_ai_video_result
from .stock_videos import load_clip_manifest, load_clip_result, video_clips_available
from .visuals import load_scene_manifest, visuals_available


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
    ai_video_paths = _ai_scene_video_paths(video_dir)
    if len(ai_video_paths) >= 4:
        return _render_ai_scene_video(
            video_dir=video_dir,
            plan=plan,
            video_paths=ai_video_paths,
            duration_seconds=duration_seconds,
            preview=preview,
        )

    clip_paths = _video_clip_paths(video_dir)
    if len(clip_paths) >= 3:
        return _render_clip_video(
            video_dir=video_dir,
            plan=plan,
            clip_paths=clip_paths,
            duration_seconds=duration_seconds,
            preview=preview,
        )

    visual_images = _scene_images(video_dir)
    if len(visual_images) >= 4:
        return _render_scene_video(
            video_dir=video_dir,
            plan=plan,
            image_paths=visual_images,
            duration_seconds=duration_seconds,
            preview=preview,
        )

    category = plan.get("trend", {}).get("category", "Trend")
    subtitle_text = clean_subtitle_text(plan, duration_seconds)

    with tempfile.TemporaryDirectory() as temp_dir:
        render_subtitles_path = Path(temp_dir) / "render-subtitles.srt"
        render_subtitles_path.write_text(make_render_subtitles(subtitle_text, duration_seconds), encoding="utf-8")

        filtergraph = ",".join(
            [
                "format=yuv420p",
                _draw_background_overlay(category, width, height),
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
            command.extend(["-i", str(voiceover_path)])

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
            command.extend(["-map", "1:a:0", "-c:a", "aac", "-b:a", "160k", "-shortest"])

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
        "visuals_used": False,
        "warning": _combine_warnings(
            "REAL VIDEO CLIPS AND VISUALS NOT GENERATED: rendered fallback background.",
            None if voiceover_path.exists() else "Rendered silent video: voiceover.mp3 not found.",
        ),
    }


def _render_ai_scene_video(
    *,
    video_dir: Path,
    plan: dict,
    video_paths: list[Path],
    duration_seconds: int,
    preview: bool,
) -> dict:
    voiceover_path = video_dir / "voiceover.mp3"
    output_path = video_dir / ("preview.mp4" if preview else "final.mp4")
    thumbnail_path = video_dir / ("preview-thumbnail.jpg" if preview else "thumbnail.jpg")
    width = PREVIEW_WIDTH if preview else WIDTH
    height = PREVIEW_HEIGHT if preview else HEIGHT
    selected_videos, scene_duration = _select_scene_timing(video_paths, duration_seconds)
    subtitle_text = clean_subtitle_text(plan, duration_seconds)

    with tempfile.TemporaryDirectory() as temp_dir:
        render_subtitles_path = Path(temp_dir) / "render-subtitles.srt"
        render_subtitles_path.write_text(make_render_subtitles(subtitle_text, duration_seconds), encoding="utf-8")
        command = ["ffmpeg", "-y"]
        for scene_path in selected_videos:
            command.extend(["-stream_loop", "-1", "-t", f"{scene_duration:.3f}", "-i", str(scene_path)])
        audio_index = len(selected_videos)
        if voiceover_path.exists():
            command.extend(["-i", str(voiceover_path)])
        filtergraph = _clip_filtergraph(
            clip_count=len(selected_videos),
            width=width,
            height=height,
            subtitles_path=render_subtitles_path,
            preview=preview,
        )
        command.extend(["-filter_complex", filtergraph, "-map", "[vout]"])
        if voiceover_path.exists():
            command.extend(["-map", f"{audio_index}:a:0", "-c:a", "aac", "-b:a", "160k", "-shortest"])
        command.extend(
            [
                "-t",
                str(duration_seconds),
                "-c:v",
                "libx264",
                "-preset",
                "ultrafast" if preview else "medium",
                "-crf",
                "25" if preview else "20",
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
                str(output_path),
            ]
        )
        completed = subprocess.run(command, capture_output=True, text=True, timeout=300)

    if completed.returncode != 0:
        return {
            "video_dir": str(video_dir),
            "rendered": False,
            "output": None,
            "warning": "FFmpeg AI scene video render failed.",
            "stderr": completed.stderr[-2000:],
            "ai_scene_videos_used": True,
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
        "ai_scene_videos_used": True,
        "scene_video_count": len(selected_videos),
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


def _render_scene_video(
    *,
    video_dir: Path,
    plan: dict,
    image_paths: list[Path],
    duration_seconds: int,
    preview: bool,
) -> dict:
    subtitles_path = video_dir / "subtitles.srt"
    voiceover_path = video_dir / "voiceover.mp3"
    output_path = video_dir / ("preview.mp4" if preview else "final.mp4")
    thumbnail_path = video_dir / ("preview-thumbnail.jpg" if preview else "thumbnail.jpg")
    width = PREVIEW_WIDTH if preview else WIDTH
    height = PREVIEW_HEIGHT if preview else HEIGHT
    selected_images, scene_duration = _select_scene_timing(image_paths, duration_seconds)
    subtitle_text = clean_subtitle_text(plan, duration_seconds)

    with tempfile.TemporaryDirectory() as temp_dir:
        render_subtitles_path = Path(temp_dir) / "render-subtitles.srt"
        render_subtitles_path.write_text(make_render_subtitles(subtitle_text, duration_seconds), encoding="utf-8")

        command = ["ffmpeg", "-y"]
        for image_path in selected_images:
            command.extend(["-i", str(image_path)])
        audio_index = len(selected_images)
        if voiceover_path.exists():
            command.extend(["-i", str(voiceover_path)])

        filtergraph = _scene_filtergraph(
            scene_count=len(selected_images),
            frames=max(1, int(scene_duration * FPS)),
            width=width,
            height=height,
            subtitles_path=render_subtitles_path if subtitles_path.exists() else None,
            preview=preview,
        )
        command.extend(["-filter_complex", filtergraph, "-map", "[vout]"])
        if voiceover_path.exists():
            command.extend(["-map", f"{audio_index}:a:0", "-c:a", "aac", "-b:a", "160k", "-shortest"])
        command.extend(
            [
                "-t",
                str(duration_seconds),
                "-c:v",
                "libx264",
                "-preset",
                "ultrafast" if preview else "medium",
                "-crf",
                "27" if preview else "22",
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
                str(output_path),
            ]
        )

        completed = subprocess.run(command, capture_output=True, text=True, timeout=240)

    if completed.returncode != 0:
        return {
            "video_dir": str(video_dir),
            "rendered": False,
            "output": None,
            "warning": "FFmpeg scene render failed.",
            "stderr": completed.stderr[-2000:],
            "visuals_used": True,
        }

    thumbnail_result = _create_scene_thumbnail(selected_images[0], thumbnail_path)
    if not preview:
        preview_thumb = video_dir / "preview-thumbnail.jpg"
        if not preview_thumb.exists() and thumbnail_path.exists():
            shutil.copyfile(thumbnail_path, preview_thumb)

    return {
        "video_dir": str(video_dir),
        "rendered": True,
        "output": str(output_path),
        "thumbnail": str(thumbnail_path) if thumbnail_path.exists() else None,
        "thumbnail_warning": thumbnail_result.get("warning"),
        "audio_used": voiceover_path.exists(),
        "preview": preview,
        "visuals_used": True,
        "scene_count": len(selected_images),
        "warning": None if voiceover_path.exists() else "Rendered silent video: voiceover.mp3 not found.",
    }


def _render_clip_video(
    *,
    video_dir: Path,
    plan: dict,
    clip_paths: list[Path],
    duration_seconds: int,
    preview: bool,
) -> dict:
    voiceover_path = video_dir / "voiceover.mp3"
    output_path = video_dir / ("preview.mp4" if preview else "final.mp4")
    thumbnail_path = video_dir / ("preview-thumbnail.jpg" if preview else "thumbnail.jpg")
    width = PREVIEW_WIDTH if preview else WIDTH
    height = PREVIEW_HEIGHT if preview else HEIGHT
    selected_clips, scene_duration = _select_scene_timing(clip_paths, duration_seconds)
    subtitle_text = clean_subtitle_text(plan, duration_seconds)

    with tempfile.TemporaryDirectory() as temp_dir:
        render_subtitles_path = Path(temp_dir) / "render-subtitles.srt"
        render_subtitles_path.write_text(make_render_subtitles(subtitle_text, duration_seconds), encoding="utf-8")

        command = ["ffmpeg", "-y"]
        for clip_path in selected_clips:
            command.extend(["-stream_loop", "-1", "-t", f"{scene_duration:.3f}", "-i", str(clip_path)])
        audio_index = len(selected_clips)
        if voiceover_path.exists():
            command.extend(["-i", str(voiceover_path)])

        filtergraph = _clip_filtergraph(
            clip_count=len(selected_clips),
            width=width,
            height=height,
            subtitles_path=render_subtitles_path,
            preview=preview,
        )
        command.extend(["-filter_complex", filtergraph, "-map", "[vout]"])
        if voiceover_path.exists():
            command.extend(["-map", f"{audio_index}:a:0", "-c:a", "aac", "-b:a", "160k", "-shortest"])
        command.extend(
            [
                "-t",
                str(duration_seconds),
                "-c:v",
                "libx264",
                "-preset",
                "ultrafast" if preview else "medium",
                "-crf",
                "26" if preview else "21",
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
                str(output_path),
            ]
        )
        completed = subprocess.run(command, capture_output=True, text=True, timeout=300)

    if completed.returncode != 0:
        return {
            "video_dir": str(video_dir),
            "rendered": False,
            "output": None,
            "warning": "FFmpeg stock clip render failed.",
            "stderr": completed.stderr[-2000:],
            "video_clips_used": True,
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
        "video_clips_used": True,
        "clip_count": len(selected_clips),
        "warning": None if voiceover_path.exists() else "Rendered silent video: voiceover.mp3 not found.",
    }


def _video_clip_paths(video_dir: Path) -> list[Path]:
    if not video_clips_available(video_dir):
        return []
    manifest = load_clip_result(video_dir) or load_clip_manifest(video_dir)
    clips = []
    for clip in manifest.get("clips", []):
        path = video_dir / clip.get("file", "")
        if path.exists():
            clips.append(path)
    return clips[:8]


def _ai_scene_video_paths(video_dir: Path) -> list[Path]:
    if not ai_scene_videos_available(video_dir):
        return []
    result = load_ai_video_result(video_dir)
    videos = []
    for scene in result.get("scenes", []):
        if not scene.get("file"):
            continue
        path = video_dir / scene["file"]
        if path.exists():
            videos.append(path)
    if not videos:
        videos = sorted((video_dir / "scene-videos").glob("scene-*.mp4"))
    return videos[:8]


def _scene_images(video_dir: Path) -> list[Path]:
    if not visuals_available(video_dir):
        return []
    manifest = load_scene_manifest(video_dir)
    images = []
    for scene in manifest.get("scenes", []):
        path = video_dir / scene.get("image", "")
        if path.exists():
            images.append(path)
    return images[:8]


def _select_scene_timing(image_paths: list[Path], duration_seconds: int) -> tuple[list[Path], float]:
    target_count = max(4, min(8, round(duration_seconds / 3)))
    selected = image_paths[: min(len(image_paths), target_count)]
    while len(selected) < 4 and image_paths:
        selected.append(image_paths[len(selected) % len(image_paths)])
    scene_duration = duration_seconds / max(len(selected), 1)
    scene_duration = max(2.0, min(4.0, scene_duration))
    return selected, scene_duration


def _clip_filtergraph(
    *,
    clip_count: int,
    width: int,
    height: int,
    subtitles_path: Path,
    preview: bool,
) -> str:
    parts = []
    for index in range(clip_count):
        parts.append(
            f"[{index}:v]"
            f"scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height},"
            f"fps={FPS},setsar=1,format=yuv420p[v{index}]"
        )
    concat_inputs = "".join(f"[v{index}]" for index in range(clip_count))
    parts.append(f"{concat_inputs}concat=n={clip_count}:v=1:a=0,format=yuv420p[base]")
    parts.append(f"[base]{_subtitles_filter(subtitles_path, preview=preview)}[vout]")
    return ";".join(parts)


def _scene_filtergraph(
    *,
    scene_count: int,
    frames: int,
    width: int,
    height: int,
    subtitles_path: Path | None,
    preview: bool,
) -> str:
    parts = []
    for index in range(scene_count):
        direction = index % 4
        if direction == 0:
            x_expr = "iw/2-(iw/zoom/2)"
            y_expr = "ih/2-(ih/zoom/2)"
        elif direction == 1:
            x_expr = f"(iw-iw/zoom)*on/{frames}"
            y_expr = "ih/2-(ih/zoom/2)"
        elif direction == 2:
            x_expr = f"(iw-iw/zoom)*(1-on/{frames})"
            y_expr = "ih/2-(ih/zoom/2)"
        else:
            x_expr = "iw/2-(iw/zoom/2)"
            y_expr = f"(ih-ih/zoom)*on/{frames}"

        parts.append(
            f"[{index}:v]"
            f"scale={int(width * 1.14)}:{int(height * 1.14)}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height},"
            f"zoompan=z='1+0.055*on/{frames}':x='{x_expr}':y='{y_expr}':d={frames}:s={width}x{height}:fps={FPS},"
            f"setsar=1[v{index}]"
        )

    concat_inputs = "".join(f"[v{index}]" for index in range(scene_count))
    parts.append(f"{concat_inputs}concat=n={scene_count}:v=1:a=0,format=yuv420p[base]")
    if subtitles_path:
        parts.append(f"[base]{_subtitles_filter(subtitles_path, preview=preview)}[vout]")
    else:
        parts.append("[base]format=yuv420p[vout]")
    return ";".join(parts)


def _create_scene_thumbnail(image_path: Path, thumbnail_path: Path) -> dict:
    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(image_path),
        "-vf",
        f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,crop={WIDTH}:{HEIGHT}",
        "-frames:v",
        "1",
        "-q:v",
        "3",
        str(thumbnail_path),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, timeout=60)
    if completed.returncode != 0:
        shutil.copyfile(image_path, thumbnail_path)
        return {"created": True, "warning": completed.stderr[-1000:]}
    return {"created": True, "warning": None}


def _combine_warnings(*warnings: str | None) -> str | None:
    active = [warning for warning in warnings if warning]
    return " ".join(active) if active else None


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
    fontsize = 14 if preview else 23
    x = 42 if preview else 82
    y = 112 if preview else 215
    boxborderw = 7 if preview else 11
    return (
        "drawtext="
        f"fontfile='{_ffmpeg_path(_font_path())}':"
        f"textfile='{_ffmpeg_path(title_path)}':"
        "fontcolor=white:"
        f"fontsize={fontsize}:"
        f"line_spacing={4 if preview else 7}:"
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
        f"fontsize={10 if preview else 17}:"
        f"x={42 if preview else 82}:"
        f"y={42 if preview else 78}:"
        "box=1:"
        "boxcolor=black@0.22:"
        f"boxborderw={4 if preview else 7}"
    )


def _subtitles_filter(subtitles_path: Path, preview: bool = False) -> str:
    fontsize = 28 if preview else 46
    margin_v = 96 if preview else 190
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
        narration = "Nobody expected this. Then everything changed."
    words = narration.split()
    max_words = 28 if duration_seconds <= PREVIEW_DURATION_SECONDS else 72
    return " ".join(words[:max_words])


def make_render_subtitles(text: str, duration_seconds: int) -> str:
    words = text.split()
    if not words:
        return ""
    chunk_size = 1
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
