from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from .planner import build_daily_network_plan, write_video_packages
from .renderer import render_video_dirs
from .sample_data import SAMPLE_TRENDS
from .sources import collect_live_trends
from .status_store import StatusStore
from .tts import synthesize_voiceovers_for_dirs


def run_daily(
    *,
    sample: bool,
    region: str,
    limit: int,
    top_n: int,
    output_dir: Path,
    channel_name: str,
    render: bool = False,
    upload: bool = False,
    tts_provider: str = "mock",
) -> dict:
    trends = SAMPLE_TRENDS if sample else collect_live_trends(region=region, limit=limit)
    plan = build_daily_network_plan(trends=trends, channel_name=channel_name, top_n=top_n)

    run_dir = output_dir / datetime.now(timezone.utc).strftime("%Y-%m-%d")
    run_dir.mkdir(parents=True, exist_ok=True)

    report_path = run_dir / "daily-trend-report.json"
    report_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    written_video_files = write_video_packages(plan, run_dir)
    package_dirs = sorted({path.parent for path in written_video_files})
    tts_result = synthesize_voiceovers_for_dirs(package_dirs, provider_name=tts_provider)

    render_result = None
    if render:
        render_result = render_video_dirs(package_dirs)

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
        "tts": tts_result,
        "render_requested": render,
        "mp4_rendered": render_result["rendered_count"] if render_result else 0,
        "final_mp4_paths": render_result["outputs"] if render_result else [],
        "render_warnings": render_result["warnings"] if render_result else [],
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
