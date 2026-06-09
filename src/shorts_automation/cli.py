from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .dashboard import serve_dashboard
from .planner import build_daily_network_plan, write_video_packages
from .renderer import DEFAULT_DURATION_SECONDS, PREVIEW_DURATION_SECONDS, render_all, render_video_package
from .runner import run_daily
from .sample_data import SAMPLE_TRENDS
from .tts import synthesize_voiceovers


def main(argv: list[str] | None = None) -> int:
    load_env_file(Path(".env"))

    parser = argparse.ArgumentParser(prog="shorts-trends")
    subparsers = parser.add_subparsers(dest="command", required=True)

    daily_parser = subparsers.add_parser("daily-run", help="Collect trends, score them, and prepare Shorts packages.")
    daily_parser.add_argument("--sample", action="store_true", help="Use bundled sample trend data.")
    daily_parser.add_argument("--region", default=os.getenv("TREND_REGION_CODE", "US"))
    daily_parser.add_argument("--channel-name", default=os.getenv("CHANNEL_NAME", "Masyra Labs"))
    daily_parser.add_argument("--limit", type=int, default=int(os.getenv("TREND_SOURCE_LIMIT", "50")))
    daily_parser.add_argument("--top-n", type=int, default=int(os.getenv("TREND_TOP_N", "10")))
    daily_parser.add_argument("--output-dir", default=os.getenv("SHORTS_OUTPUT_DIR", "outputs"))
    daily_parser.add_argument("--render", action="store_true", help="Render final.mp4 files with FFmpeg when available.")
    daily_parser.add_argument("--upload", action="store_true", help="Reserved for explicit YouTube upload. Disabled without OAuth integration.")
    daily_parser.add_argument("--tts-provider", default=os.getenv("TTS_PROVIDER", "elevenlabs"), choices=["mock", "elevenlabs", "off"])
    daily_parser.add_argument("--quick-preview", action="store_true", help="Render 15 second low-resolution preview.mp4 files.")
    daily_parser.add_argument("--preview-only", action="store_true", help="Render preview.mp4 and thumbnail only; skip final.mp4.")

    render_parser = subparsers.add_parser("render-video", help="Render one prepared video package directory.")
    render_parser.add_argument("video_dir", help="Directory containing video-plan.json and subtitles.srt.")
    render_parser.add_argument("--quick-preview", action="store_true", help="Render preview.mp4 instead of final.mp4.")
    render_parser.add_argument("--preview-only", action="store_true", help="Alias for --quick-preview.")

    generate_parser = subparsers.add_parser("generate-video", help="Generate sample video packages and optionally render them.")
    generate_parser.add_argument("--channel-name", default=os.getenv("CHANNEL_NAME", "Masyra Labs"))
    generate_parser.add_argument("--output-dir", default=os.getenv("SHORTS_OUTPUT_DIR", "outputs"))
    generate_parser.add_argument("--top-n", type=int, default=1)
    generate_parser.add_argument("--render", action="store_true")
    generate_parser.add_argument("--tts-provider", default=os.getenv("TTS_PROVIDER", "elevenlabs"), choices=["mock", "elevenlabs", "off"])
    generate_parser.add_argument("--quick-preview", action="store_true")

    tts_parser = subparsers.add_parser("generate-tts", help="Generate voiceover.mp3 files when a TTS provider is available.")
    tts_parser.add_argument("video_root", help="Directory containing video package folders.")
    tts_parser.add_argument("--tts-provider", default=os.getenv("TTS_PROVIDER", "elevenlabs"), choices=["mock", "elevenlabs", "off"])

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
            render=args.render,
            upload=args.upload,
            tts_provider=args.tts_provider,
            quick_preview=args.quick_preview,
            preview_only=args.preview_only,
        )
        print(json.dumps(summary, ensure_ascii=False))
        return 0

    if args.command == "render-video":
        result = render_video_package(
            Path(args.video_dir),
            duration_seconds=PREVIEW_DURATION_SECONDS if args.quick_preview or args.preview_only else DEFAULT_DURATION_SECONDS,
            preview=args.quick_preview or args.preview_only,
        )
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result["rendered"] or result.get("warning") else 1

    if args.command == "generate-video":
        output_dir = Path(args.output_dir) / "generated-video"
        output_dir.mkdir(parents=True, exist_ok=True)
        plan = build_daily_network_plan(SAMPLE_TRENDS, channel_name=args.channel_name, top_n=args.top_n)
        package_files = write_video_packages(plan, output_dir)
        tts_result = synthesize_voiceovers(output_dir / "videos", provider_name=args.tts_provider)
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
                    "mp4_rendered": render_result["rendered_count"] if render_result else 0,
                    "final_mp4_paths": render_result["outputs"] if render_result else [],
                    "render_warnings": render_result["warnings"] if render_result else [],
                },
                ensure_ascii=False,
            )
        )
        return 0

    if args.command == "generate-tts":
        result = synthesize_voiceovers(Path(args.video_root), provider_name=args.tts_provider)
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


if __name__ == "__main__":
    raise SystemExit(main())
