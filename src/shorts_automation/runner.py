from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from .learning import ensure_learning_db, record_generated_package
from .planner import build_daily_network_plan, write_video_packages
from .quality import score_video_dirs
from .renderer import DEFAULT_DURATION_SECONDS, PREVIEW_DURATION_SECONDS, render_video_dirs
from .sample_data import SAMPLE_TRENDS
from .sources import collect_live_trends
from .status_store import StatusStore
from .stock_videos import generate_video_clips_for_dirs
from .tts import synthesize_voiceovers_for_dirs
from .visuals import generate_visuals_for_dirs


def run_daily(
    *,
    sample: bool,
    region: str,
    limit: int,
    top_n: int,
    output_dir: Path,
    channel_name: str,
    categories: list[str] | None = None,
    render: bool = False,
    upload: bool = False,
    tts_provider: str = "elevenlabs",
    image_provider: str = "auto",
    video_provider: str = "auto",
    quick_preview: bool = False,
    preview_only: bool = False,
) -> dict:
    trends = SAMPLE_TRENDS if sample else collect_live_trends(region=region, limit=limit)
    if categories:
        allowed = {category.strip().lower() for category in categories if category.strip()}
        trends = [trend for trend in trends if trend.get("category", "").lower() in allowed]
    plan = build_daily_network_plan(trends=trends, channel_name=channel_name, top_n=top_n)

    run_dir = output_dir / datetime.now(timezone.utc).strftime("%Y-%m-%d")
    run_dir.mkdir(parents=True, exist_ok=True)

    report_path = run_dir / "daily-trend-report.json"
    report_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    written_video_files = write_video_packages(plan, run_dir)
    package_dirs = sorted({path.parent for path in written_video_files})
    learning_db = ensure_learning_db(output_dir)
    for item, package_dir in zip(plan["items"], package_dirs):
        record_generated_package(package_dir, item, learning_db)
    tts_result = synthesize_voiceovers_for_dirs(package_dirs, provider_name=tts_provider)

    render_result = None
    preview_result = None
    visuals_result = None
    clips_result = None
    if render:
        clips_result = generate_video_clips_for_dirs(package_dirs, provider_name=video_provider)
        visuals_result = generate_visuals_for_dirs(package_dirs, provider_name=image_provider)
        preview_result = render_video_dirs(
            package_dirs,
            duration_seconds=PREVIEW_DURATION_SECONDS,
            preview=True,
        )
        if not preview_only:
            render_result = render_video_dirs(
                package_dirs,
                duration_seconds=DEFAULT_DURATION_SECONDS,
                preview=False,
            )
        quality_result = score_video_dirs(package_dirs)
    else:
        quality_result = score_video_dirs(package_dirs)

    upload_result = {
        "enabled": upload,
        "attempted": False,
        "warning": None,
    }
    if upload:
        upload_result = _evaluate_upload_gate(run_dir)

    summary = {
        "run_dir": str(run_dir),
        "trend_report": str(report_path),
        "trends_analyzed": len(trends),
        "videos_prepared": len(plan["items"]),
        "video_files_written": len(written_video_files),
        "learning_db": str(learning_db),
        "tts": tts_result,
        "visuals": visuals_result,
        "video_clips": clips_result,
        "quality": quality_result,
        "render_requested": render,
        "quick_preview": quick_preview or render,
        "preview_only": preview_only,
        "mp4_rendered": render_result["rendered_count"] if render_result else 0,
        "final_mp4_paths": render_result["outputs"] if render_result else [],
        "preview_mp4_rendered": preview_result["rendered_count"] if preview_result else 0,
        "preview_mp4_paths": preview_result["outputs"] if preview_result else [],
        "thumbnail_paths": _thumbnail_paths(visuals_result, render_result, preview_result),
        "render_warnings": (render_result["warnings"] if render_result else []) + (preview_result["warnings"] if preview_result else []),
        "upload": upload_result,
        "mode": "sample" if sample else "live",
    }
    summary_path = run_dir / "daily-run-summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def _evaluate_upload_gate(run_dir: Path) -> dict:
    if not _oauth_configured():
        return {
            "enabled": True,
            "attempted": False,
            "warning": "Upload disabled: YouTube OAuth is not configured.",
        }

    store = StatusStore(run_dir.parent / "review-status.json")
    approved = []
    for video_dir in sorted((run_dir / "videos").glob("*")):
        if not video_dir.is_dir():
            continue
        if store.get(video_dir)["status"] == "Approved" and (video_dir / "final.mp4").exists():
            approved.append(str(video_dir))

    if not approved:
        return {
            "enabled": True,
            "attempted": False,
            "warning": "Upload disabled: no Approved video packages with final.mp4.",
        }

    return {
        "enabled": True,
        "attempted": False,
        "warning": "Upload gate passed, but uploader is intentionally not implemented in this build.",
        "approved_ready": approved,
    }


def _oauth_configured() -> bool:
    return bool(os.getenv("YOUTUBE_OAUTH_CLIENT_ID") and os.getenv("YOUTUBE_OAUTH_CLIENT_SECRET"))


def _thumbnail_paths(visuals_result: dict | None, render_result: dict | None, preview_result: dict | None) -> list[str]:
    paths: list[str] = []
    if visuals_result:
        paths.extend(
            str(result["thumbnail"])
            for result in visuals_result.get("results", [])
            if result.get("thumbnail")
        )
    if render_result:
        paths.extend(render_result.get("thumbnails", []))
    if preview_result:
        paths.extend(preview_result.get("thumbnails", []))
    return paths
