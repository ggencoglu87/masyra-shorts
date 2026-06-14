from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .ai_video import default_ai_video_provider, generate_ai_videos_for_dirs, generate_ai_videos_for_package
from .character_bible import write_character_bible
from .dashboard import serve_dashboard
from .planner import build_daily_network_plan, write_video_packages
from .renderer import DEFAULT_DURATION_SECONDS, PREVIEW_DURATION_SECONDS, render_all, render_video_package
from .runner import run_daily
from .sample_data import SAMPLE_TRENDS
from .stock_videos import default_video_provider, generate_video_clips_for_dirs, generate_video_clips_for_package
from .tts import synthesize_voiceover, synthesize_voiceovers
from .visuals import default_visual_provider, generate_visuals_for_dirs, generate_visuals_for_package


def main(argv: list[str] | None = None) -> int:
    load_env_file(Path(".env"))

    parser = argparse.ArgumentParser(prog="shorts-trends")
    subparsers = parser.add_subparsers(dest="command", required=True)

    daily_parser = subparsers.add_parser("daily-run", help="Collect trends, score them, and prepare Shorts packages.")
    daily_parser.add_argument("--sample", action="store_true", help="Use bundled sample trend data.")
    daily_parser.add_argument("--region", default=os.getenv("TREND_REGION_CODE", "US"))
    daily_parser.add_argument("--channel-name", default=os.getenv("CHANNEL_NAME", "Masyra Labs"))
    daily_parser.add_argument("--categories", default=os.getenv("CONTENT_CATEGORIES", ""), help="Comma-separated category filter, e.g. AI,Gaming,Animals.")
    daily_parser.add_argument("--limit", type=int, default=int(os.getenv("TREND_SOURCE_LIMIT", "50")))
    daily_parser.add_argument("--top-n", type=int, default=int(os.getenv("TREND_TOP_N", "10")))
    daily_parser.add_argument("--output-dir", default=os.getenv("SHORTS_OUTPUT_DIR", "outputs"))
    daily_parser.add_argument("--render", action="store_true", default=True, help="Render final.mp4 files with FFmpeg when available. Enabled by default in v3.")
    daily_parser.add_argument("--no-render", action="store_false", dest="render", help="Prepare story packages and voiceover only; skip clips, visuals, and video rendering.")
    daily_parser.add_argument("--upload", action="store_true", help="Reserved for explicit YouTube upload. Disabled without OAuth integration.")
    tts_choices = ["auto", "google_ai_studio", "google", "mock", "elevenlabs", "piper", "off"]
    daily_parser.add_argument("--tts-provider", default=os.getenv("TTS_PROVIDER", "auto"), choices=tts_choices)
    visual_choices = ["auto", "openai", "placeholder"]
    daily_parser.add_argument("--image-provider", default=default_visual_provider(), choices=visual_choices)
    daily_parser.add_argument("--video-provider", default=default_video_provider(), choices=["auto", "pexels", "pixabay", "off"])
    ai_video_choices = ["off", "auto", "veo3", "veo3fast", "veo", "runway", "kling", "pixverse", "hailuo", "replicate", "ltx", "scene_image_motion"]
    daily_parser.add_argument("--ai-video-provider", default=default_ai_video_provider(), choices=ai_video_choices)
    daily_parser.add_argument("--quick-preview", action="store_true", help="Render 15 second low-resolution preview.mp4 files.")
    daily_parser.add_argument("--preview-only", action="store_true", help="Render preview.mp4 and thumbnail only; skip final.mp4.")

    render_parser = subparsers.add_parser("render-video", help="Render one prepared video package directory.")
    render_parser.add_argument("video_dir", help="Directory containing video-plan.json and subtitles.srt.")
    render_parser.add_argument("--quick-preview", action="store_true", help="Render preview.mp4 instead of final.mp4.")
    render_parser.add_argument("--preview-only", action="store_true", help="Alias for --quick-preview.")
    render_parser.add_argument("--with-audio", action="store_true", help="Generate voiceover.mp3 before rendering when missing.")
    render_parser.add_argument("--with-visuals", action="store_true", help="Generate scene images before rendering when missing.")
    render_parser.add_argument("--with-clips", action="store_true", help="Download stock video clips before rendering when available.")
    render_parser.add_argument("--with-ai-video", action="store_true", help="Generate AI scene videos before rendering when configured.")
    render_parser.add_argument("--video-provider", default=default_video_provider(), choices=["auto", "pexels", "pixabay", "off"])
    render_parser.add_argument("--ai-video-provider", default=default_ai_video_provider(), choices=ai_video_choices)
    render_parser.add_argument("--image-provider", default=default_visual_provider(), choices=visual_choices)
    render_parser.add_argument("--force-visuals", action="store_true", help="Regenerate existing scene images before rendering.")
    render_parser.add_argument("--allow-placeholder", action="store_true", help="Allow placeholder fallback if OpenAI visual generation fails.")
    render_parser.add_argument("--debug", action="store_true", help="Write debug payloads to visual-result.json.")
    render_parser.add_argument("--tts-provider", default=os.getenv("TTS_PROVIDER", "auto"), choices=tts_choices)
    render_parser.add_argument("--force-tts", action="store_true", help="Regenerate voiceover.mp3 before rendering.")

    visuals_parser = subparsers.add_parser("generate-visuals", help="Generate scene images from asset-prompts.json.")
    visuals_parser.add_argument("video_dir", help="Video package directory containing asset-prompts.json.")
    visuals_parser.add_argument("--image-provider", default=default_visual_provider(), choices=visual_choices)
    visuals_parser.add_argument("--force", action="store_true", help="Overwrite existing scene images.")
    visuals_parser.add_argument("--allow-placeholder", action="store_true", help="Allow placeholder fallback if OpenAI visual generation fails.")
    visuals_parser.add_argument("--debug", action="store_true", help="Write debug payloads to visual-result.json.")

    visuals_all_parser = subparsers.add_parser("generate-visuals-all", help="Generate scene images for every package in a videos directory.")
    visuals_all_parser.add_argument("videos_dir", help="Directory containing video package folders.")
    visuals_all_parser.add_argument("--image-provider", default=default_visual_provider(), choices=visual_choices)
    visuals_all_parser.add_argument("--force", action="store_true", help="Overwrite existing scene images.")
    visuals_all_parser.add_argument("--allow-placeholder", action="store_true", help="Allow placeholder fallback if OpenAI visual generation fails.")
    visuals_all_parser.add_argument("--debug", action="store_true", help="Write debug payloads to visual-result.json.")

    clips_parser = subparsers.add_parser("generate-video-clips", help="Download licensed stock video clips for one package.")
    clips_parser.add_argument("video_dir", help="Video package directory containing asset-prompts.json.")
    clips_parser.add_argument("--video-provider", default=default_video_provider(), choices=["auto", "pexels", "pixabay", "off"])
    clips_parser.add_argument("--force", action="store_true", help="Overwrite existing downloaded clips.")
    clips_parser.add_argument("--debug", action="store_true", help="Write provider HTTP error details to video-clips-result.json.")

    clips_all_parser = subparsers.add_parser("generate-video-clips-all", help="Download licensed stock video clips for every package in a videos directory.")
    clips_all_parser.add_argument("videos_dir", help="Directory containing video package folders.")
    clips_all_parser.add_argument("--video-provider", default=default_video_provider(), choices=["auto", "pexels", "pixabay", "off"])
    clips_all_parser.add_argument("--force", action="store_true", help="Overwrite existing downloaded clips.")
    clips_all_parser.add_argument("--debug", action="store_true", help="Write provider HTTP error details to each video-clips-result.json.")

    character_parser = subparsers.add_parser("generate-character-bible", help="Generate character_bible.json for one package.")
    character_parser.add_argument("video_dir", help="Video package directory containing video-plan.json.")

    ai_video_parser = subparsers.add_parser("generate-ai-video", help="Generate AI scene videos for one package.")
    ai_video_parser.add_argument("video_dir", help="Video package directory containing storyboard.json.")
    ai_video_parser.add_argument("--ai-video-provider", default=default_ai_video_provider(), choices=ai_video_choices)
    ai_video_parser.add_argument("--force", action="store_true", help="Regenerate existing scene videos.")

    ai_video_all_parser = subparsers.add_parser("generate-ai-video-all", help="Generate AI scene videos for every package in a videos directory.")
    ai_video_all_parser.add_argument("videos_dir", help="Directory containing video package folders.")
    ai_video_all_parser.add_argument("--ai-video-provider", default=default_ai_video_provider(), choices=ai_video_choices)
    ai_video_all_parser.add_argument("--force", action="store_true", help="Regenerate existing scene videos.")

    generate_parser = subparsers.add_parser("generate-video", help="Generate sample video packages and optionally render them.")
    generate_parser.add_argument("--channel-name", default=os.getenv("CHANNEL_NAME", "Masyra Labs"))
    generate_parser.add_argument("--output-dir", default=os.getenv("SHORTS_OUTPUT_DIR", "outputs"))
    generate_parser.add_argument("--top-n", type=int, default=1)
    generate_parser.add_argument("--render", action="store_true")
    generate_parser.add_argument("--tts-provider", default=os.getenv("TTS_PROVIDER", "auto"), choices=tts_choices)
    generate_parser.add_argument("--image-provider", default=default_visual_provider(), choices=visual_choices)
    generate_parser.add_argument("--quick-preview", action="store_true")

    tts_parser = subparsers.add_parser("generate-tts", help="Generate voiceover.mp3 for one video package.")
    tts_parser.add_argument("video_dir", help="Directory containing voiceover.txt.")
    tts_parser.add_argument("--tts-provider", default=os.getenv("TTS_PROVIDER", "auto"), choices=tts_choices)
    tts_parser.add_argument("--force", action="store_true", help="Regenerate voiceover.mp3 even when it already exists.")

    tts_all_parser = subparsers.add_parser("generate-tts-all", help="Generate voiceover.mp3 files for every package in a videos directory.")
    tts_all_parser.add_argument("videos_dir", help="Directory containing video package folders.")
    tts_all_parser.add_argument("--tts-provider", default=os.getenv("TTS_PROVIDER", "auto"), choices=tts_choices)
    tts_all_parser.add_argument("--force", action="store_true", help="Regenerate existing voiceover.mp3 files.")

    dashboard_parser = subparsers.add_parser("dashboard", help="Start the local review dashboard.")
    dashboard_parser.add_argument("--output-dir", default=os.getenv("SHORTS_OUTPUT_DIR", "outputs"))
    dashboard_parser.add_argument("--host", default="127.0.0.1")
    dashboard_parser.add_argument("--port", type=int, default=8765)

    args = parser.parse_args(argv)

    if args.command == "daily-run":
        summary = run_daily(
            sample=args.sample,
            region=args.region,
            limit=args.limit,
            top_n=args.top_n,
            output_dir=Path(args.output_dir),
            channel_name=args.channel_name,
            categories=_split_csv(args.categories),
            render=args.render,
            upload=args.upload,
            tts_provider=args.tts_provider,
            image_provider=args.image_provider,
            video_provider=args.video_provider,
            ai_video_provider=args.ai_video_provider,
            quick_preview=args.quick_preview,
            preview_only=args.preview_only,
        )
        print(json.dumps(summary, ensure_ascii=False))
        return 0

    if args.command == "render-video":
        tts_result = None
        if args.with_audio:
            tts_result = synthesize_voiceover(
                Path(args.video_dir),
                provider_name=args.tts_provider,
                force=args.force_tts,
            )
        visuals_result = None
        clips_result = None
        ai_video_result = None
        if args.with_ai_video:
            ai_video_result = generate_ai_videos_for_package(
                Path(args.video_dir),
                provider_name=args.ai_video_provider,
                force=args.force_visuals,
            )
        if args.with_clips:
            clips_result = generate_video_clips_for_package(
                Path(args.video_dir),
                provider_name=args.video_provider,
                force=args.force_visuals,
            )
        if args.with_visuals:
            visuals_result = generate_visuals_for_package(
                Path(args.video_dir),
                provider_name=args.image_provider,
                force=args.force_visuals,
                allow_placeholder=args.allow_placeholder,
                debug=args.debug,
            )
        result = render_video_package(
            Path(args.video_dir),
            duration_seconds=PREVIEW_DURATION_SECONDS if args.quick_preview or args.preview_only else DEFAULT_DURATION_SECONDS,
            preview=args.quick_preview or args.preview_only,
        )
        envelope = {"tts": tts_result, "ai_video": ai_video_result, "clips": clips_result, "visuals": visuals_result, "render": result}
        print(json.dumps(envelope if tts_result or visuals_result or clips_result or ai_video_result else result, ensure_ascii=False))
        return 0 if result["rendered"] or result.get("warning") else 1

    if args.command == "generate-visuals":
        path = Path(args.video_dir)
        result = generate_visuals_for_package(
            path,
            provider_name=args.image_provider,
            force=args.force,
            allow_placeholder=args.allow_placeholder,
            debug=args.debug,
        )
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if args.command == "generate-visuals-all":
        path = Path(args.videos_dir)
        video_dirs = [
            child for child in sorted(path.iterdir())
            if child.is_dir() and (child / "video-plan.json").exists()
        ]
        result = generate_visuals_for_dirs(
            video_dirs,
            provider_name=args.image_provider,
            force=args.force,
            allow_placeholder=args.allow_placeholder,
            debug=args.debug,
        )
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if args.command == "generate-video-clips":
        result = generate_video_clips_for_package(Path(args.video_dir), provider_name=args.video_provider, force=args.force, debug=args.debug)
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if args.command == "generate-video-clips-all":
        path = Path(args.videos_dir)
        video_dirs = [
            child for child in sorted(path.iterdir())
            if child.is_dir() and (child / "video-plan.json").exists()
        ]
        result = generate_video_clips_for_dirs(video_dirs, provider_name=args.video_provider, force=args.force, debug=args.debug)
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if args.command == "generate-character-bible":
        path = Path(args.video_dir)
        plan_path = path / "video-plan.json"
        plan = json.loads(plan_path.read_text(encoding="utf-8")) if plan_path.exists() else {}
        category = plan.get("trend", {}).get("category", "Reddit Stories")
        result = write_character_bible(path, category)
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if args.command == "generate-ai-video":
        result = generate_ai_videos_for_package(Path(args.video_dir), provider_name=args.ai_video_provider, force=args.force)
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if args.command == "generate-ai-video-all":
        path = Path(args.videos_dir)
        video_dirs = [
            child for child in sorted(path.iterdir())
            if child.is_dir() and (child / "storyboard.json").exists()
        ]
        result = generate_ai_videos_for_dirs(video_dirs, provider_name=args.ai_video_provider, force=args.force)
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if args.command == "generate-video":
        output_dir = Path(args.output_dir) / "generated-video"
        output_dir.mkdir(parents=True, exist_ok=True)
        plan = build_daily_network_plan(SAMPLE_TRENDS, channel_name=args.channel_name, top_n=args.top_n)
        package_files = write_video_packages(plan, output_dir)
        tts_result = synthesize_voiceovers(output_dir / "videos", provider_name=args.tts_provider)
        video_dirs = [
            child for child in sorted((output_dir / "videos").iterdir())
            if child.is_dir() and (child / "video-plan.json").exists()
        ]
        visuals_result = generate_visuals_for_dirs(video_dirs, provider_name=args.image_provider) if args.render else None
        render_result = (
            render_all(
                output_dir / "videos",
                duration_seconds=PREVIEW_DURATION_SECONDS if args.quick_preview else DEFAULT_DURATION_SECONDS,
                preview=args.quick_preview,
            )
            if args.render
            else None
        )
        print(
            json.dumps(
                {
                    "output_dir": str(output_dir),
                    "videos_prepared": len(plan["items"]),
                    "package_files_written": len(package_files),
                    "tts": tts_result,
                    "visuals": visuals_result,
                    "mp4_rendered": render_result["rendered_count"] if render_result else 0,
                    "final_mp4_paths": render_result["outputs"] if render_result else [],
                    "render_warnings": render_result["warnings"] if render_result else [],
                },
                ensure_ascii=False,
            )
        )
        return 0

    if args.command == "generate-tts":
        result = synthesize_voiceover(Path(args.video_dir), provider_name=args.tts_provider, force=args.force)
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if args.command == "generate-tts-all":
        result = synthesize_voiceovers(Path(args.videos_dir), provider_name=args.tts_provider, force=args.force)
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if args.command == "dashboard":
        serve_dashboard(output_dir=Path(args.output_dir), host=args.host, port=args.port)
        return 0

    return 1


def load_env_file(path: Path) -> None:
    if not path.exists():
        return

    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


if __name__ == "__main__":
    raise SystemExit(main())
