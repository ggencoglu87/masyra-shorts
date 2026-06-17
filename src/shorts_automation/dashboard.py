from __future__ import annotations

import html
import json
import mimetypes
import os
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .ai_video import default_ai_video_provider, generate_ai_videos_for_package, load_ai_video_result, load_providers_status
from .quality import load_quality_score, score_video_package
from .renderer import DEFAULT_DURATION_SECONDS, PREVIEW_DURATION_SECONDS, render_video_package
from .status_store import DEFAULT_STATUS, StatusStore, VALID_STATUSES
from .stock_videos import default_video_provider, generate_video_clips_for_package, load_clip_manifest, load_clip_result
from .tts import synthesize_voiceover, tts_status
from .visuals import default_visual_provider, generate_visuals_for_package, load_scene_manifest, load_visual_result


STATUS_ORDER = ["Needs Edit", "Approved", "Rejected", "Publish Ready"]
SORT_OPTIONS = {
    "viral": ("Viral score", "viral_score"),
    "trend": ("Trend score", "trend_score"),
    "growth": ("Growth score", "growth_score"),
    "hook": ("Hook score", "hook_score"),
    "shareability": ("Shareability score", "shareability_score"),
}


def serve_dashboard(output_dir: Path, host: str = "127.0.0.1", port: int = 8765) -> None:
    output_dir = output_dir.resolve()
    store = StatusStore(output_dir / "review-status.json")

    class DashboardHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path == "/":
                params = urllib.parse.parse_qs(parsed.query)
                self._send_html(
                    render_index(
                        output_dir,
                        store,
                        status_filter=params.get("status", ["all"])[0],
                        sort_key=params.get("sort", ["viral"])[0],
                    )
                )
                return
            if parsed.path == "/video":
                params = urllib.parse.parse_qs(parsed.query)
                video_dir = _safe_video_dir(output_dir, params.get("dir", [""])[0])
                if not video_dir:
                    self._send_text("Invalid video dir", status=404)
                    return
                self._send_html(render_video_detail(output_dir, store, video_dir))
                return
            if parsed.path == "/media":
                params = urllib.parse.parse_qs(parsed.query)
                media_path = _safe_media_path(output_dir, params.get("path", [""])[0])
                if not media_path:
                    self._send_text("Invalid media path", status=404)
                    return
                self._send_file(media_path, download=params.get("download", ["0"])[0] == "1")
                return
            self._send_text("Not found", status=404)

        def do_POST(self) -> None:
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path == "/action":
                self._handle_action()
                return
            if parsed.path != "/status":
                self._send_text("Not found", status=404)
                return

            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length).decode("utf-8")
            params = urllib.parse.parse_qs(body)
            video_dir = _safe_video_dir(output_dir, params.get("dir", [""])[0])
            status = params.get("status", [DEFAULT_STATUS])[0]
            notes = params.get("notes", [""])[0]
            return_to = params.get("return_to", ["detail"])[0]

            if not video_dir or status not in VALID_STATUSES:
                self._send_text("Invalid status update", status=400)
                return

            store.set(video_dir, status=status, notes=notes)
            if return_to == "index":
                target = "/"
            else:
                target = "/video?dir=" + urllib.parse.quote(str(video_dir.relative_to(output_dir)))
            self.send_response(303)
            self.send_header("Location", target)
            self.end_headers()

        def _handle_action(self) -> None:
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length).decode("utf-8")
            params = urllib.parse.parse_qs(body)
            video_dir = _safe_video_dir(output_dir, params.get("dir", [""])[0])
            action = params.get("action", [""])[0]

            if not video_dir:
                self._send_text("Invalid video dir", status=400)
                return

            if action == "generate_visuals":
                generate_visuals_for_package(video_dir, provider_name=params.get("provider", [default_visual_provider()])[0], force=False)
            elif action == "generate_clips":
                generate_video_clips_for_package(video_dir, provider_name=params.get("provider", [default_video_provider()])[0], force=False)
            elif action == "generate_tts":
                synthesize_voiceover(video_dir, provider_name=params.get("provider", [_dashboard_tts_provider()])[0], force=False)
            elif action == "generate_ai_video":
                generate_ai_videos_for_package(video_dir, provider_name=params.get("provider", [default_ai_video_provider()])[0], force=False)
            elif action == "rerender":
                render_video_package(video_dir, duration_seconds=PREVIEW_DURATION_SECONDS, preview=True)
                render_video_package(video_dir, duration_seconds=DEFAULT_DURATION_SECONDS, preview=False)
                score_video_package(video_dir)
            elif action == "rerender_visuals":
                generate_visuals_for_package(video_dir, provider_name=params.get("provider", [default_visual_provider()])[0], force=False)
                render_video_package(video_dir, duration_seconds=PREVIEW_DURATION_SECONDS, preview=True)
                render_video_package(video_dir, duration_seconds=DEFAULT_DURATION_SECONDS, preview=False)
                score_video_package(video_dir)
            elif action == "rerender_audio":
                synthesize_voiceover(video_dir, provider_name=params.get("provider", [_dashboard_tts_provider()])[0], force=False)
                render_video_package(video_dir, duration_seconds=PREVIEW_DURATION_SECONDS, preview=True)
                render_video_package(video_dir, duration_seconds=DEFAULT_DURATION_SECONDS, preview=False)
                score_video_package(video_dir)
            elif action == "rerender_ai_video":
                generate_ai_videos_for_package(video_dir, provider_name=params.get("provider", [default_ai_video_provider()])[0], force=False)
                render_video_package(video_dir, duration_seconds=PREVIEW_DURATION_SECONDS, preview=True)
                render_video_package(video_dir, duration_seconds=DEFAULT_DURATION_SECONDS, preview=False)
                score_video_package(video_dir)
            else:
                self._send_text("Invalid action", status=400)
                return

            target = "/video?dir=" + urllib.parse.quote(str(video_dir.relative_to(output_dir)))
            self.send_response(303)
            self.send_header("Location", target)
            self.end_headers()

        def log_message(self, format: str, *args: object) -> None:
            return

        def _send_html(self, body: str, status: int = 200) -> None:
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(body.encode("utf-8"))

        def _send_text(self, body: str, status: int = 200) -> None:
            self.send_response(status)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(body.encode("utf-8"))

        def _send_file(self, path: Path, download: bool = False) -> None:
            content_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
            if path.suffix.lower() in {".jpg", ".jpeg"}:
                try:
                    with path.open("rb") as file:
                        if file.read(8) == b"\x89PNG\r\n\x1a\n":
                            content_type = "image/png"
                except OSError:
                    pass
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            if download:
                self.send_header("Content-Disposition", f'attachment; filename="{path.name}"')
            self.end_headers()
            self.wfile.write(path.read_bytes())

    server = ThreadingHTTPServer((host, port), DashboardHandler)
    print(f"Dashboard: http://{host}:{port}")
    server.serve_forever()


def render_index(output_dir: Path, store: StatusStore, status_filter: str = "all", sort_key: str = "viral") -> str:
    packages = build_package_rows(output_dir, store)
    summary = summarize(packages)
    sort_label, score_key = SORT_OPTIONS.get(sort_key, SORT_OPTIONS["viral"])
    filtered = [
        package for package in packages
        if status_filter == "all"
        or package["status"] == status_filter
        or (status_filter == "Publish Ready" and package["publish_ready"])
    ]
    filtered.sort(key=lambda item: item["scores"].get(score_key, 0), reverse=True)

    cards = "".join(render_package_card(output_dir, package) for package in filtered)
    empty = '<section class="empty">No videos match this filter.</section>' if not filtered else ""

    return page(
        "Masyra Labs Review Dashboard",
        f"""
        <header class="hero">
          <div>
            <p class="eyebrow">Masyra Labs</p>
            <h1>Review Dashboard</h1>
            <p class="muted">Review trend packages, inspect assets, approve the good ones, and keep upload gated.</p>
          </div>
        </header>
        <section class="summary">
          {summary_card("Total Videos", summary["total"], "total")}
          {summary_card("Approved", summary["Approved"], "approved")}
          {summary_card("Rejected", summary["Rejected"], "rejected")}
          {summary_card("Needs Edit", summary["Needs Edit"], "needs-edit")}
        </section>
        <section class="controls">
          <form method="get" action="/">
            <label>Status
              <select name="status">
                {filter_options(status_filter)}
              </select>
            </label>
            <label>Sort
              <select name="sort">
                {sort_options(sort_key)}
              </select>
            </label>
            <button type="submit">Apply</button>
          </form>
          <p class="muted">Showing {len(filtered)} videos sorted by {_e(sort_label)}.</p>
        </section>
        <main class="cards">{cards}</main>
        {empty}
        """,
    )


def render_package_card(output_dir: Path, package: dict) -> str:
    video_dir = package["video_dir"]
    detail_url = "/video?dir=" + urllib.parse.quote(str(video_dir.relative_to(output_dir)))
    scores = package["scores"]
    return f"""
    <article class="card">
      <a class="thumb-link" href="{detail_url}">{_thumbnail_html(output_dir, video_dir)}</a>
      <div class="card-body">
        <div class="card-topline">
          <span class="pill status-{slug(package["status"])}">{_e(package["status"])}</span>
          <span class="pill">{_e(package["category"])}</span>
          {visual_badge(package)}
          {ai_video_badge(package["asset_status"].get("ai_videos_ready"))}
          {character_badge(package["asset_status"].get("character_bible_ready"))}
          {audio_badge(package["audio_ready"])}
          {clip_badge(package["clips_ready"])}
        </div>
        <h2><a href="{detail_url}">{_e(package["trend_title"])}</a></h2>
        <div class="score-grid">
          {score_box("Hook", scores.get("hook_score", ""))}
          {score_box("Viral", scores.get("viral_score", scores.get("viral_potential_score", "")))}
          {score_box("Share", scores.get("shareability_score", ""))}
          {score_box("Complete", scores.get("completion_probability", ""))}
        </div>
        <form class="inline-actions" method="post" action="/status">
          <input type="hidden" name="dir" value="{_e(str(video_dir.relative_to(output_dir)))}">
          <input type="hidden" name="return_to" value="index">
          {status_button("Approved", "Approve")}
          {status_button("Rejected", "Reject")}
          {status_button("Needs Edit", "Needs Edit")}
        </form>
      </div>
    </article>
    """


def render_video_detail(output_dir: Path, store: StatusStore, video_dir: Path) -> str:
    plan = _read_json(video_dir / "video-plan.json")
    upload = _read_json(video_dir / "upload-metadata.json")
    prompts = _read_json(video_dir / "asset-prompts.json")
    storyboard = _read_json(video_dir / "storyboard.json")
    captions = _read_json(video_dir / "captions.json")
    character_bible = _read_json(video_dir / "character_bible.json")
    manifest = load_scene_manifest(video_dir)
    clip_manifest = load_clip_manifest(video_dir)
    clip_result = load_clip_result(video_dir)
    ai_video_result = load_ai_video_result(video_dir)
    providers_status = load_providers_status(video_dir)
    visual_result = load_visual_result(video_dir)
    quality = load_quality_score(video_dir)
    status_data = store.get(video_dir)
    final_mp4 = video_dir / "final.mp4"
    preview_mp4 = video_dir / "preview.mp4"
    voiceover_mp3 = video_dir / "voiceover.mp3"
    tts_result = _read_json(video_dir / "tts-result.json")
    tts_integrity = tts_status(video_dir)
    requested_tts_provider = tts_result.get("requested_provider") or tts_result.get("provider", "not generated")
    provider_used = tts_result.get("provider_used") or tts_result.get("provider", "not generated")
    asset_status = dashboard_asset_status(video_dir)
    rel = str(video_dir.relative_to(output_dir))
    download = _download_link(output_dir, final_mp4)
    visual_warning = ""
    if not asset_status["clips_ready"] and not asset_status["real_openai_visuals_ready"] and not asset_status["placeholder_visuals"]:
        visual_warning = '<div class="visual-warning">VISUALS NOT GENERATED</div>'
    elif asset_status["placeholder_warning"]:
        visual_warning = '<div class="visual-warning">Placeholder visuals only — not ready for publishing.</div>'
    audio_warning = ""
    if (final_mp4.exists() or preview_mp4.exists()) and not asset_status["audio_ready"]:
        audio_warning = '<div class="warning">Silent render: voiceover.mp3 is missing. Add ElevenLabs audio and rerender for voice.</div>'

    return page(
        plan.get("title", "Video package"),
        f"""
        <header class="detail-header">
          <a href="/" class="back-link">Back to dashboard</a>
          <div class="detail-title-row">
            <div>
              <p class="eyebrow">{_e(plan.get("trend", {}).get("category", ""))}</p>
              <h1>{_e(plan.get("title", video_dir.name))}</h1>
            </div>
            <span class="pill status-{slug(status_data["status"])}">{_e(status_data["status"])}</span>
          </div>
        </header>
        <section class="detail-grid">
          <div class="video-panel">
            <h2>Final Video</h2>
            {visual_warning}
            {audio_warning}
            {_video_html(output_dir, final_mp4, "No final.mp4 yet")}
            {download}
          </div>
          <div class="review-panel">
            <h2>Review Decision</h2>
            <form method="post" action="/status">
              <input type="hidden" name="dir" value="{_e(rel)}">
              <textarea name="notes" placeholder="Review notes">{_e(status_data.get("notes", ""))}</textarea>
              <div class="review-actions">
                {status_button("Approved", "Approve")}
                {status_button("Rejected", "Reject")}
                {status_button("Needs Edit", "Needs Edit")}
              </div>
            </form>
            <h2>Production Actions</h2>
            <form class="production-actions" method="post" action="/action">
              <input type="hidden" name="dir" value="{_e(rel)}">
              <input type="hidden" name="action" value="generate_clips">
              <input type="hidden" name="provider" value="{_e(default_video_provider())}">
              <button type="submit">Generate Video Clips</button>
            </form>
            <form class="production-actions" method="post" action="/action">
              <input type="hidden" name="dir" value="{_e(rel)}">
              <input type="hidden" name="action" value="generate_visuals">
              <input type="hidden" name="provider" value="{_e(default_visual_provider())}">
              <button type="submit">Generate Visuals</button>
            </form>
            <form class="production-actions" method="post" action="/action">
              <input type="hidden" name="dir" value="{_e(rel)}">
              <input type="hidden" name="action" value="generate_ai_video">
              <input type="hidden" name="provider" value="{_e(default_ai_video_provider())}">
              <button type="submit">Generate AI Videos</button>
            </form>
            <form class="production-actions" method="post" action="/action">
              <input type="hidden" name="dir" value="{_e(rel)}">
              <input type="hidden" name="action" value="generate_tts">
              <input type="hidden" name="provider" value="{_e(_dashboard_tts_provider())}">
              <button type="submit">Generate Voiceover</button>
            </form>
            <form class="production-actions" method="post" action="/action">
              <input type="hidden" name="dir" value="{_e(rel)}">
              <input type="hidden" name="action" value="rerender">
              <button type="submit">Re-render Video</button>
            </form>
            <form class="production-actions" method="post" action="/action">
              <input type="hidden" name="dir" value="{_e(rel)}">
              <input type="hidden" name="action" value="rerender_visuals">
              <input type="hidden" name="provider" value="{_e(default_visual_provider())}">
              <button type="submit">Re-render With Visuals</button>
            </form>
            <form class="production-actions" method="post" action="/action">
              <input type="hidden" name="dir" value="{_e(rel)}">
              <input type="hidden" name="action" value="rerender_audio">
              <input type="hidden" name="provider" value="{_e(_dashboard_tts_provider())}">
              <button type="submit">Re-render With Audio</button>
            </form>
            <form class="production-actions" method="post" action="/action">
              <input type="hidden" name="dir" value="{_e(rel)}">
              <input type="hidden" name="action" value="rerender_ai_video">
              <input type="hidden" name="provider" value="{_e(default_ai_video_provider())}">
              <button type="submit">Re-render From AI Videos</button>
            </form>
            <h2>Quick Preview</h2>
            {_video_html(output_dir, preview_mp4, "No preview.mp4 yet")}
            <h2>Voiceover Audio</h2>
            <p class="muted">Requested provider: {_e(requested_tts_provider)}</p>
            <p class="muted">Actual provider used: {_e(provider_used)}</p>
            {tts_integrity_section(tts_integrity)}
            {_audio_html(output_dir, voiceover_mp3)}
          </div>
        </section>
        <section class="score-strip">
          {score_box("Viral", plan.get("scores", {}).get("viral_potential_score", ""))}
          {score_box("Viral", plan.get("scores", {}).get("viral_score", ""))}
          {score_box("Hook", plan.get("scores", {}).get("hook_score", ""))}
          {score_box("Shareability", plan.get("scores", {}).get("shareability_score", ""))}
          {score_box("Completion", plan.get("scores", {}).get("completion_probability", ""))}
          {score_box("Trend", plan.get("scores", {}).get("trend_score", ""))}
          {score_box("Growth", plan.get("scores", {}).get("growth_score", ""))}
          {score_box("Momentum", plan.get("scores", {}).get("momentum_score", ""))}
        {score_box("Competition", plan.get("scores", {}).get("competition_score", ""))}
        </section>
        {quality_section(quality)}
        {asset_status_section(asset_status)}
        {providers_status_section(providers_status)}
        {character_bible_section(character_bible)}
        {storyboard_section(storyboard)}
        {captions_section(captions)}
        {voice_profile_section(plan)}
        {ai_video_section(output_dir, video_dir, ai_video_result)}
        {clip_section(output_dir, video_dir, clip_manifest, clip_result)}
        {scene_timeline(output_dir, video_dir, manifest, asset_status)}
        {file_section("video-clips-manifest.json", json.dumps(clip_manifest, ensure_ascii=False, indent=2))}
        {file_section("video-clips-result.json", json.dumps(clip_result, ensure_ascii=False, indent=2))}
        {file_section("ai-video-result.json", json.dumps(ai_video_result, ensure_ascii=False, indent=2))}
        {file_section("character_bible.json", json.dumps(character_bible, ensure_ascii=False, indent=2))}
        {file_section("quality-result.json", json.dumps(quality, ensure_ascii=False, indent=2))}
        {file_section("visual-result.json", json.dumps(visual_result, ensure_ascii=False, indent=2))}
        {file_section("script.txt", _read_text(video_dir / "script.txt"))}
        {file_section("voiceover.txt", _read_text(video_dir / "voiceover.txt"))}
        {file_section("tts-result.json", json.dumps(tts_result, ensure_ascii=False, indent=2))}
        {file_section("subtitles.srt", _read_text(video_dir / "subtitles.srt"))}
        {file_section("upload-metadata.json", json.dumps(upload, ensure_ascii=False, indent=2))}
        {file_section("render-brief.txt", _read_text(video_dir / "render-brief.txt"))}
        {file_section("asset-prompts.json", json.dumps(prompts, ensure_ascii=False, indent=2))}
        {file_section("storyboard.json", json.dumps(storyboard, ensure_ascii=False, indent=2))}
        {file_section("captions.json", json.dumps(captions, ensure_ascii=False, indent=2))}
        """,
    )


def build_package_rows(output_dir: Path, store: StatusStore) -> list[dict]:
    rows = []
    for video_dir in find_video_packages(output_dir):
        plan = _read_json(video_dir / "video-plan.json")
        status = store.get(video_dir)["status"]
        asset_status = dashboard_asset_status(video_dir)
        rows.append(
            {
                "video_dir": video_dir,
                "status": status,
                "trend_title": plan.get("trend", {}).get("title", video_dir.name),
                "category": plan.get("trend", {}).get("category", ""),
                "channel_target": plan.get("channel_target", ""),
                "scores": plan.get("scores", {}),
                "visuals_ready": asset_status["visuals_ready"],
                "audio_ready": asset_status["audio_ready"],
                "clips_ready": asset_status["clips_ready"],
                "publish_ready": asset_status["publish_ready"],
                "asset_status": asset_status,
            }
        )
    return rows


def summarize(packages: list[dict]) -> dict:
    summary = {"total": len(packages), "Approved": 0, "Rejected": 0, "Needs Edit": 0}
    for package in packages:
        summary[package["status"]] = summary.get(package["status"], 0) + 1
    return summary


def find_video_packages(output_dir: Path) -> list[Path]:
    return sorted(
        [path for path in output_dir.glob("*/videos/*") if path.is_dir() and (path / "video-plan.json").exists()],
        reverse=True,
    )


def summary_card(label: str, value: int, class_name: str) -> str:
    return f'<div class="summary-card {class_name}"><span>{_e(label)}</span><strong>{value}</strong></div>'


def score_box(label: str, value: object) -> str:
    return f'<div class="score-box"><span>{_e(label)}</span><strong>{_e(value)}</strong></div>'


def status_button(status: str, label: str) -> str:
    return f'<button class="btn btn-{slug(status)}" type="submit" name="status" value="{_e(status)}">{_e(label)}</button>'


def dashboard_asset_status(video_dir: Path) -> dict:
    clip_result = load_clip_result(video_dir)
    ai_video_result = load_ai_video_result(video_dir)
    visual_result = load_visual_result(video_dir)
    scene_manifest = load_scene_manifest(video_dir)
    tts_result = _read_json(video_dir / "tts-result.json")
    final_exists = (video_dir / "final.mp4").exists()
    ai_generated_count = int(ai_video_result.get("generated_count", 0) or 0)
    real_ai_scene_count = int(ai_video_result.get("real_ai_scene_count", 0) or 0)
    image_motion_scene_count = int(ai_video_result.get("image_motion_scene_count", 0) or 0)
    image_only_scene_count = int(ai_video_result.get("image_only_scene_count", 0) or 0)
    ai_videos_ready = real_ai_scene_count >= 4
    real_clip_count = int(clip_result.get("real_clip_count", 0) or 0)
    clip_count = int(clip_result.get("clip_count", 0) or 0)
    clips_ready = real_clip_count >= 3 and final_exists
    real_openai_visuals_ready = bool(visual_result.get("real_visuals_ready"))
    placeholder_visuals = _placeholder_visuals(scene_manifest, visual_result)
    audio_ready = bool(tts_result.get("audio_matches_current_text") and tts_result.get("mixed_voiceover_ready", (video_dir / "voiceover.mp3").exists()))
    estimated_episode_duration = float(tts_result.get("estimated_episode_duration") or _storyboard_duration(video_dir) or 0)
    dialogue_percentage = float(tts_result.get("dialogue_percentage") or _dialogue_percentage(video_dir) or 0)
    dialogue_line_count = int(tts_result.get("dialogue_line_count") or _dialogue_line_count(video_dir) or 0)
    speaker_count = int(tts_result.get("speaker_count") or len(tts_result.get("voices_used", [])) or _speaker_count(video_dir) or 0)
    provider_used = tts_result.get("provider_used") or tts_result.get("provider")
    min_lines_pass = dialogue_line_count >= 20
    min_duration_pass = estimated_episode_duration >= 25
    caption_validation_pass = _caption_validation(video_dir)
    ai_movie_ready = bool(
        ai_videos_ready
        and final_exists
        and ai_video_result.get("character_consistency_score", 0) >= 75
        and ai_video_result.get("visual_quality_score", 0) >= 75
        and ai_video_result.get("motion_quality_score", 0) >= 70
    )
    publish_ready = bool(
        ai_movie_ready
        and audio_ready
        and min_duration_pass
        and dialogue_percentage >= 30
        and min_lines_pass
        and caption_validation_pass
    )
    return {
        "character_bible_ready": (video_dir / "character_bible.json").exists(),
        "final_mp4": final_exists,
        "ai_videos_ready": ai_videos_ready,
        "ai_movie_ready": ai_movie_ready,
        "ai_video_provider": ai_video_result.get("provider", "off"),
        "ai_provider_fallback_chain": ai_video_result.get("provider_priority", []),
        "ai_generation_duration": _ai_generation_duration(ai_video_result),
        "ai_scene_count": int(ai_video_result.get("scene_count", 0) or 0),
        "ai_generated_count": ai_generated_count,
        "real_ai_scene_count": real_ai_scene_count,
        "image_motion_scene_count": image_motion_scene_count,
        "image_only_scene_count": image_only_scene_count,
        "character_consistency_score": ai_video_result.get("character_consistency_score", 0),
        "visual_quality_score": ai_video_result.get("visual_quality_score", 0),
        "motion_quality_score": ai_video_result.get("motion_quality_score", 0),
        "clip_count": clip_count,
        "real_clip_count": real_clip_count,
        "clips_ready": clips_ready,
        "video_provider": clip_result.get("provider", "unknown"),
        "video_publish_ready": bool(clip_result.get("publish_ready")),
        "audio_ready": audio_ready,
        "audio_provider": provider_used or "not generated",
        "voice_mode": tts_result.get("voice_mode", "single"),
        "voices_used": tts_result.get("voices_used", []),
        "speaker_count": speaker_count,
        "estimated_episode_duration": estimated_episode_duration,
        "dialogue_percentage": dialogue_percentage,
        "dialogue_line_count": dialogue_line_count,
        "min_lines_pass": min_lines_pass,
        "min_duration_pass": min_duration_pass,
        "caption_validation_pass": caption_validation_pass,
        "voice_separation_mode": tts_result.get("voice_separation_mode", "single"),
        "narrator_ready": bool(tts_result.get("narrator_ready", audio_ready)),
        "character_voices_ready": bool(tts_result.get("character_voices_ready", audio_ready)),
        "mixed_voiceover_ready": bool(tts_result.get("mixed_voiceover_ready", audio_ready)),
        "audio_generation_time": tts_result.get("generation_time"),
        "requested_audio_provider": tts_result.get("requested_provider") or tts_result.get("provider", "not generated"),
        "real_openai_visuals_ready": real_openai_visuals_ready,
        "placeholder_visuals": placeholder_visuals,
        "placeholder_warning": bool(not clips_ready and not real_openai_visuals_ready and placeholder_visuals),
        "visuals_ready": bool(ai_videos_ready or clips_ready or real_openai_visuals_ready),
        "publish_ready": publish_ready,
    }


def visual_badge(package: dict) -> str:
    status = package.get("asset_status", {})
    if status.get("ai_videos_ready"):
        return '<span class="pill status-approved">AI VIDEO</span>'
    if status.get("image_motion_scene_count", 0) >= 4:
        return '<span class="pill status-needs-edit">IMAGE MOTION</span>'
    if status.get("image_only_scene_count", 0) >= 4:
        return '<span class="pill status-needs-edit">IMAGE ONLY</span>'
    if status.get("clips_ready"):
        return '<span class="pill status-needs-edit">Stock Fallback Used</span>'
    if status.get("real_openai_visuals_ready"):
        return '<span class="pill status-needs-edit">IMAGE ONLY</span>'
    return '<span class="pill status-rejected">VISUALS NOT GENERATED</span>'


def ai_video_badge(ready: bool) -> str:
    if ready:
        return '<span class="pill status-approved">AI Movie Mode</span>'
    return '<span class="pill status-needs-edit">AI Videos Missing</span>'


def character_badge(ready: bool) -> str:
    if ready:
        return '<span class="pill status-approved">Character Bible Ready</span>'
    return '<span class="pill status-needs-edit">Character Bible Missing</span>'


def audio_badge(ready: bool) -> str:
    if ready:
        return '<span class="pill status-approved">Voiceover Ready</span>'
    return '<span class="pill status-needs-edit">Voiceover Missing</span>'


def clip_badge(ready: bool) -> str:
    if ready:
        return '<span class="pill status-approved">Clips Ready</span>'
    return '<span class="pill status-needs-edit">Clips Missing</span>'


def filter_options(current: str) -> str:
    options = [("all", "All"), *[(status, status) for status in STATUS_ORDER]]
    return "".join(
        f'<option value="{_e(value)}" {"selected" if value == current else ""}>{_e(label)}</option>'
        for value, label in options
    )


def sort_options(current: str) -> str:
    return "".join(
        f'<option value="{_e(value)}" {"selected" if value == current else ""}>{_e(label)}</option>'
        for value, (label, _score_key) in SORT_OPTIONS.items()
    )


def file_section(title: str, content: str) -> str:
    return f'<section class="file-section"><h2>{_e(title)}</h2><pre>{_e(content)}</pre></section>'


def quality_section(quality: dict) -> str:
    if not quality:
        return '<section class="score-strip"><div class="missing">No quality-result.json yet.</div></section>'
    return f"""
    <section class="score-strip">
      {score_box("Retention", quality.get("retention_score", ""))}
      {score_box("Hook", quality.get("hook_score", ""))}
      {score_box("Visual", quality.get("visual_score", ""))}
      {score_box("Publish", quality.get("publish_score", ""))}
    </section>
    """


def asset_status_section(status: dict) -> str:
    return f"""
    <section class="score-strip">
      {score_box("AI Provider", status.get("ai_video_provider", ""))}
      {score_box("Fallback Chain", ", ".join(status.get("ai_provider_fallback_chain", [])) or "missing")}
      {score_box("Video Gen Time", status.get("ai_generation_duration", "missing"))}
      {score_box("AI Scenes", f"{status.get('ai_generated_count', 0)}/{status.get('ai_scene_count', 0)}")}
      {score_box("Real AI Scenes", status.get("real_ai_scene_count", 0))}
      {score_box("Image Motion", status.get("image_motion_scene_count", 0))}
      {score_box("Image Only", status.get("image_only_scene_count", 0))}
      {score_box("Character Consistency", status.get("character_consistency_score", 0))}
      {score_box("Motion Quality", status.get("motion_quality_score", 0))}
      {score_box("Clip Count", status.get("clip_count", 0))}
      {score_box("Real Clips", status.get("real_clip_count", 0))}
      {score_box("Video Provider", status.get("video_provider", ""))}
      {score_box("Audio Provider", status.get("audio_provider", ""))}
      {score_box("Voice Mode", status.get("voice_mode", "single"))}
      {score_box("Voice Separation", status.get("voice_separation_mode", "single"))}
      {score_box("Voices Used", ", ".join(status.get("voices_used", [])) or "missing")}
      {score_box("Speaker Count", status.get("speaker_count", 0))}
      {score_box("Est. Duration", f"{status.get('estimated_episode_duration', 0)}s")}
      {score_box("Dialogue %", f"{status.get('dialogue_percentage', 0)}%")}
      {score_box("Dialogue Lines", status.get("dialogue_line_count", 0))}
      {score_box("Min Lines", "PASS" if status.get("min_lines_pass") else "FAIL")}
      {score_box("Min Duration", "PASS" if status.get("min_duration_pass") else "FAIL")}
      {score_box("Caption Validation", "PASS" if status.get("caption_validation_pass") else "FAIL")}
      {score_box("Narrator Ready", "Yes" if status.get("narrator_ready") else "No")}
      {score_box("Character Voices", "Yes" if status.get("character_voices_ready") else "No")}
      {score_box("Mixed Voiceover", "Yes" if status.get("mixed_voiceover_ready") else "No")}
      {score_box("Voice Gen Time", status.get("audio_generation_time", "missing"))}
      {score_box("Publish Ready", "Yes" if status.get("publish_ready") else "No")}
    </section>
    """


def providers_status_section(status: dict) -> str:
    providers = status.get("providers", {}) if isinstance(status, dict) else {}
    if not providers:
        return '<section class="timeline-section"><h2>Provider Status</h2><div class="missing">providers-status.json missing. Generate AI videos to populate provider health.</div></section>'
    cards = []
    for provider in providers.values():
        state = "Available" if provider.get("available") else "Unavailable"
        configured = "Configured" if provider.get("configured") else "Not configured"
        cards.append(
            f"""
            <article class="scene-card">
              <div class="scene-body">
                <h3>{_e(provider.get("provider", ""))}</h3>
                <div class="scene-meta">
                  <span>{_e(state)}</span>
                  <span>{_e(configured)}</span>
                  <span>avg {_e(provider.get("average_generation_time", "n/a"))}</span>
                </div>
                <p>Last success: {_e(provider.get("last_success") or "never")}</p>
                <p>Last failure: {_e(provider.get("last_failure") or "never")}</p>
                <p>{_e(provider.get("last_error") or "")}</p>
              </div>
            </article>
            """
        )
    return f"""
    <section class="timeline-section">
      <div class="section-title-row">
        <h2>Provider Status</h2>
        <span class="pill">{len(providers)} providers</span>
      </div>
      <div class="timeline-grid">{''.join(cards)}</div>
    </section>
    """


def character_bible_section(bible: object) -> str:
    if not isinstance(bible, dict) or not bible.get("characters"):
        return '<section class="timeline-section"><h2>Character Bible</h2><div class="missing">No character_bible.json yet.</div></section>'
    cards = []
    for character in bible.get("characters", []):
        cards.append(
            f"""
            <article class="scene-card">
              <div class="scene-body">
                <div class="scene-meta">
                  <span>{_e(character.get("id", ""))}</span>
                  <span>{_e(character.get("role", ""))}</span>
                </div>
                <p><strong>{_e(character.get("name", ""))}</strong></p>
                <p>{_e(character.get("visual_description", character.get("appearance", "")))}</p>
                <p>voice: {_e((character.get("voice_profile") or {}).get("speaking_style", character.get("voice", "")))}</p>
                <p>hash: {_e(character.get("appearance_hash", ""))}</p>
              </div>
            </article>
            """
        )
    return f'<section class="timeline-section"><h2>Character Bible</h2><p class="muted">{_e(bible.get("style", ""))}</p><div class="timeline-grid">{"".join(cards)}</div></section>'


def ai_video_section(output_dir: Path, video_dir: Path, result: dict) -> str:
    scenes = result.get("scenes", []) if isinstance(result, dict) else []
    if not scenes:
        return '<section class="timeline-section"><h2>AI Scene Videos</h2><div class="visual-warning">AI VIDEOS NOT GENERATED</div></section>'
    cards = []
    for scene in scenes:
        path = video_dir / scene.get("file", "")
        media = '<div class="scene-missing">Missing AI video</div>'
        if path.exists():
            media = f'<video controls muted preload="metadata" class="scene-image" src="{_media_url(output_dir, path, cache_bust=True)}"></video>'
        scene_type = _scene_type_label(scene.get("scene_type", "image_only"))
        cards.append(
            f"""
            <article class="scene-card">
              {media}
              <div class="scene-body">
                <div class="scene-meta">
                  <span>Scene {_e(scene.get("scene", ""))}</span>
                  <span>{_e(scene.get("provider", ""))}</span>
                  {scene_type}
                </div>
                <p>{_e(scene.get("warning", ""))}</p>
              </div>
            </article>
            """
        )
    return f"""
    <section class="timeline-section">
      <div class="section-title-row">
        <h2>AI Scene Videos</h2>
        <span class="pill">Provider: {_e(result.get("provider", "unknown"))}</span>
        <span class="pill">Generated: {_e(result.get("generated_count", 0))}/{_e(result.get("scene_count", 0))}</span>
        <span class="pill">AI VIDEO: {_e(result.get("real_ai_scene_count", 0))}</span>
        <span class="pill">IMAGE MOTION: {_e(result.get("image_motion_scene_count", 0))}</span>
        <span class="pill">IMAGE ONLY: {_e(result.get("image_only_scene_count", 0))}</span>
        <span class="pill">AI movie ready: {_e(result.get("ai_movie_ready", False))}</span>
      </div>
      <div class="timeline-grid">{''.join(cards)}</div>
    </section>
    """


def storyboard_section(storyboard: object) -> str:
    if not isinstance(storyboard, list) or not storyboard:
        return '<section class="timeline-section"><h2>Storyboard</h2><div class="missing">No storyboard.json yet.</div></section>'
    cards = []
    for scene in storyboard:
        cards.append(
            f"""
            <article class="scene-card">
              <div class="scene-body">
                <div class="scene-meta">
                  <span>Scene {_e(scene.get("scene", ""))}</span>
                  <span>{_e(scene.get("beat", ""))}</span>
                  <span>{_e(scene.get("time", ""))}</span>
                </div>
                <p><strong>{_e(scene.get("caption", ""))}</strong></p>
                <p>{_e(_dialogue_preview(scene.get("dialogue", [])))}</p>
                <p>{_e(", ".join(scene.get("search_queries", [])))}</p>
              </div>
            </article>
            """
        )
    return f'<section class="timeline-section"><h2>Storyboard</h2><div class="timeline-grid">{"".join(cards)}</div></section>'


def _dialogue_preview(dialogue: object) -> str:
    if not isinstance(dialogue, list):
        return ""
    return " | ".join(
        f"{str(line.get('speaker_id', '')).upper()}: {line.get('line', '')}"
        for line in dialogue
        if isinstance(line, dict) and line.get("line")
    )


def _storyboard_duration(video_dir: Path) -> float:
    storyboard = _read_json(video_dir / "storyboard.json")
    if not isinstance(storyboard, list):
        return 0.0
    return round(sum(float(scene.get("duration", 0) or 0) for scene in storyboard if isinstance(scene, dict)), 2)


def _dialogue_percentage(video_dir: Path) -> float:
    lines = _storyboard_dialogue_lines(video_dir)
    character_lines = [line for line in lines if line.get("speaker_id") != "narrator"]
    return round((len(character_lines) / max(len(lines), 1)) * 100, 2)


def _speaker_count(video_dir: Path) -> int:
    return len({line.get("speaker_id") for line in _storyboard_dialogue_lines(video_dir) if line.get("speaker_id")})


def _dialogue_line_count(video_dir: Path) -> int:
    return len([line for line in _storyboard_dialogue_lines(video_dir) if line.get("line")])


def _caption_validation(video_dir: Path) -> bool:
    captions = _read_json(video_dir / "captions.json")
    if not isinstance(captions, list) or not captions:
        return False
    for item in captions:
        if not isinstance(item, dict):
            return False
        word = str(item.get("word", ""))
        if not word or ":" in word:
            return False
    return True


def _storyboard_dialogue_lines(video_dir: Path) -> list[dict]:
    storyboard = _read_json(video_dir / "storyboard.json")
    if not isinstance(storyboard, list):
        return []
    lines = []
    for scene in storyboard:
        if isinstance(scene, dict):
            lines.extend(line for line in scene.get("dialogue", []) if isinstance(line, dict))
    return lines


def captions_section(captions: object) -> str:
    if not isinstance(captions, list) or not captions:
        return '<section class="timeline-section"><h2>Captions</h2><div class="missing">No captions.json yet.</div></section>'
    preview = " ".join(item.get("word", "") for item in captions[:24] if isinstance(item, dict))
    return f'<section class="file-section"><h2>TikTok Captions Preview</h2><pre>{_e(preview)}</pre></section>'


def voice_profile_section(plan: dict) -> str:
    profile = plan.get("voice_profile", {})
    return f"""
    <section class="score-strip">
      {score_box("Channel Target", plan.get("channel_target", ""))}
      {score_box("Voice Style", profile.get("style", ""))}
      {score_box("Voice Pace", profile.get("pace", ""))}
      {score_box("Emotion", profile.get("emotion", ""))}
    </section>
    """


def tts_integrity_section(status: dict) -> str:
    matches = status.get("audio_matches_current_text")
    match_label = "Matches current voiceover.txt" if matches else "Does not match current voiceover.txt"
    match_class = "status-approved" if matches else "status-needs-edit"
    return f"""
    <div class="tts-integrity">
      <span class="pill {match_class}">{_e(match_label)}</span>
      <dl>
        <dt>Requested provider</dt>
        <dd>{_e(status.get("requested_provider") or "missing")}</dd>
        <dt>Actual provider used</dt>
        <dd>{_e(status.get("provider_used") or "missing")}</dd>
        <dt>Voice mode</dt>
        <dd>{_e(status.get("voice_mode") or "single")}</dd>
        <dt>Voices used</dt>
        <dd>{_e(", ".join(status.get("voices_used", [])) or "missing")}</dd>
        <dt>Mixed voiceover</dt>
        <dd>{_e("ready" if status.get("mixed_voiceover_ready") else "missing")}</dd>
        <dt>Current source hash</dt>
        <dd>{_e(status.get("source_text_hash") or "missing")}</dd>
        <dt>Recorded source hash</dt>
        <dd>{_e(status.get("recorded_source_text_hash") or "missing")}</dd>
        <dt>Generated audio hash</dt>
        <dd>{_e(status.get("generated_audio_hash") or "missing")}</dd>
        <dt>Current audio hash</dt>
        <dd>{_e(status.get("current_audio_hash") or "missing")}</dd>
      </dl>
    </div>
    """


def clip_section(output_dir: Path, video_dir: Path, manifest: dict, result: dict) -> str:
    clips = result.get("clips") or manifest.get("clips", [])
    clip_count = result.get("clip_count", manifest.get("clip_count", 0))
    real_clip_count = result.get("real_clip_count", manifest.get("real_clip_count", 0))
    publish_ready = result.get("publish_ready", manifest.get("publish_ready", False))
    provider = result.get("provider", manifest.get("provider", "unknown"))
    if not clips:
        return '<section class="timeline-section"><h2>Video Clips</h2><div class="visual-warning">REAL VIDEO CLIPS NOT GENERATED</div></section>'
    cards = []
    for clip in clips:
        path = video_dir / clip.get("file", "")
        media = '<div class="scene-missing">Missing clip</div>'
        if path.exists():
            media_url = "/media?path=" + urllib.parse.quote(str(path.relative_to(output_dir)))
            media = f'<video controls muted preload="metadata" class="scene-image" src="{media_url}"></video>'
        cards.append(
            f"""
            <article class="scene-card">
              {media}
              <div class="scene-body">
                <div class="scene-meta">
                  <span>{_e(clip.get("provider", ""))}</span>
                  <span>{_e(clip.get("query", ""))}</span>
                </div>
                <p>{_e(clip.get("url", ""))}</p>
              </div>
            </article>
            """
        )
    return f"""
    <section class="timeline-section">
      <div class="section-title-row">
        <h2>Video Clips</h2>
        <span class="pill">Provider: {_e(provider)}</span>
        <span class="pill">clip_count: {_e(clip_count)}</span>
        <span class="pill">real_clip_count: {_e(real_clip_count)}</span>
        <span class="pill">publish_ready: {_e(publish_ready)}</span>
      </div>
      <div class="timeline-grid">{''.join(cards)}</div>
    </section>
    """


def scene_timeline(output_dir: Path, video_dir: Path, manifest: dict, asset_status: dict | None = None) -> str:
    scenes = manifest.get("scenes", [])
    if not scenes:
        return '<section class="timeline-section"><h2>Scene Timeline</h2><div class="visual-warning">VISUALS NOT GENERATED</div></section>'

    cards = []
    for scene in scenes:
        image = video_dir / scene.get("image", "")
        image_html = '<div class="scene-missing">Missing image</div>'
        if image.exists():
            image_url = "/media?path=" + urllib.parse.quote(str(image.relative_to(output_dir)))
            image_html = f'<img class="scene-image" src="{image_url}" alt="Scene {scene.get("scene", "")}">'
        cards.append(
            f"""
            <article class="scene-card">
              {image_html}
              <div class="scene-body">
                <div class="scene-meta">
                  <span>Scene {_e(scene.get("scene", ""))}</span>
                  <span>{_e(scene.get("duration_seconds", ""))}s</span>
                  <span>{_e(scene.get("provider", ""))}</span>
                </div>
                <p>{_e(scene.get("prompt", ""))}</p>
              </div>
            </article>
            """
        )
    return f"""
    <section class="timeline-section">
      <div class="section-title-row">
        <h2>Scene Timeline</h2>
        <span class="pill">{len(scenes)} scenes</span>
        <span class="pill">Provider: {_e(manifest.get("provider_selected", "unknown"))}</span>
      </div>
      {_placeholder_warning(manifest, asset_status or {})}
      <div class="timeline-grid">{''.join(cards)}</div>
    </section>
    """


def _placeholder_visuals(manifest: dict, visual_result: dict) -> bool:
    providers = set(visual_result.get("providers_used", []))
    providers.update(scene.get("provider") for scene in manifest.get("scenes", []) if scene.get("provider"))
    return "placeholder" in providers


def _placeholder_warning(manifest: dict, asset_status: dict | None = None) -> str:
    if asset_status and not asset_status.get("placeholder_warning"):
        return ""
    if any(scene.get("provider") == "placeholder" for scene in manifest.get("scenes", [])):
        return '<div class="visual-warning">Placeholder visuals only — not ready for publishing.</div>'
    return ""


def _scene_type_label(scene_type: str) -> str:
    labels = {
        "ai_video": "AI VIDEO",
        "image_motion": "IMAGE MOTION",
        "image_only": "IMAGE ONLY",
    }
    css = "status-approved" if scene_type == "ai_video" else "status-needs-edit"
    return f'<span class="pill {css}">{_e(labels.get(scene_type, scene_type or "IMAGE ONLY"))}</span>'


def _ai_generation_duration(result: dict) -> str:
    total = 0.0
    for scene in result.get("scenes", []):
        if scene.get("generation_time") and not scene.get("fallback_chain"):
            total += float(scene.get("generation_time") or 0)
        for attempt in scene.get("fallback_chain", []):
            total += float(attempt.get("generation_time") or 0)
    if not total:
        return "missing"
    return f"{round(total, 2)}s"


def page(title: str, body: str) -> str:
    return f"""
    <!doctype html>
    <html>
    <head>
      <meta charset="utf-8">
      <meta name="viewport" content="width=device-width, initial-scale=1">
      <title>{_e(title)}</title>
      <style>
        :root {{
          color-scheme: dark;
          --bg: #070b12;
          --panel: #101823;
          --panel-2: #141f2d;
          --ink: #eef5ff;
          --muted: #8fa1b6;
          --line: #243348;
          --green: #31d0aa;
          --red: #ff6978;
          --amber: #f7c65f;
          --blue: #68a7ff;
        }}
        * {{ box-sizing: border-box; }}
        body {{ margin: 0; font-family: Segoe UI, Arial, sans-serif; background: radial-gradient(circle at top left, #13253a, transparent 35%), var(--bg); color: var(--ink); }}
        a {{ color: inherit; text-decoration: none; }}
        h1 {{ margin: 0; font-size: clamp(30px, 4vw, 52px); letter-spacing: 0; }}
        h2 {{ margin: 0 0 14px; font-size: 18px; }}
        h3 {{ margin: 0 0 10px; font-size: 15px; }}
        .hero, .detail-header, .summary, .controls, .cards, .detail-grid, .score-strip, .file-section, .timeline-section {{ width: min(1240px, calc(100% - 32px)); margin: 18px auto; }}
        .hero, .detail-header {{ padding: 28px 0 8px; }}
        .eyebrow {{ color: var(--green); text-transform: uppercase; letter-spacing: .14em; font-size: 12px; font-weight: 700; margin: 0 0 10px; }}
        .muted {{ color: var(--muted); }}
        .summary {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 14px; }}
        .summary-card, .controls, .card, .file-section, .video-panel, .review-panel, .score-box, .timeline-section, .scene-card {{ background: color-mix(in srgb, var(--panel), transparent 4%); border: 1px solid var(--line); border-radius: 12px; }}
        .summary-card {{ padding: 18px; }}
        .summary-card span, .score-box span {{ display: block; color: var(--muted); font-size: 13px; }}
        .summary-card strong {{ font-size: 34px; display: block; margin-top: 8px; }}
        .summary-card.approved strong {{ color: var(--green); }}
        .summary-card.rejected strong {{ color: var(--red); }}
        .summary-card.needs-edit strong {{ color: var(--amber); }}
        .controls {{ padding: 16px; display: flex; align-items: center; justify-content: space-between; gap: 18px; }}
        .controls form {{ display: flex; gap: 12px; align-items: end; flex-wrap: wrap; }}
        label {{ display: grid; gap: 6px; color: var(--muted); font-size: 13px; }}
        select, textarea, button {{ font: inherit; }}
        select, textarea {{ background: #0b111a; color: var(--ink); border: 1px solid var(--line); border-radius: 8px; padding: 10px; }}
        textarea {{ width: 100%; min-height: 112px; resize: vertical; }}
        button, .download-link, .back-link {{ border: 0; border-radius: 8px; padding: 10px 14px; color: #071018; background: var(--blue); cursor: pointer; font-weight: 700; display: inline-flex; justify-content: center; }}
        .cards {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }}
        .card {{ display: grid; grid-template-columns: 116px minmax(0, 1fr); overflow: hidden; min-height: 210px; }}
        .thumb-link {{ background: #0b111a; display: block; }}
        .thumb {{ width: 100%; height: 100%; min-height: 210px; object-fit: cover; background: #17202a; }}
        .card-body {{ padding: 16px; display: grid; gap: 12px; }}
        .card h2 {{ font-size: 19px; line-height: 1.25; }}
        .card-topline, .inline-actions, .review-actions, .production-actions {{ display: flex; gap: 8px; flex-wrap: wrap; }}
        .production-actions {{ margin: 0 0 10px; }}
        .pill {{ border: 1px solid var(--line); border-radius: 999px; color: var(--muted); padding: 5px 9px; font-size: 12px; }}
        .status-approved {{ color: var(--green); border-color: color-mix(in srgb, var(--green), transparent 45%); }}
        .status-rejected {{ color: var(--red); border-color: color-mix(in srgb, var(--red), transparent 45%); }}
        .status-needs-edit {{ color: var(--amber); border-color: color-mix(in srgb, var(--amber), transparent 45%); }}
        .score-grid, .score-strip {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; }}
        .score-strip {{ grid-template-columns: repeat(4, minmax(0, 1fr)); }}
        .score-box {{ padding: 12px; }}
        .score-box strong {{ display: block; margin-top: 5px; font-size: 20px; }}
        .btn-approved {{ background: var(--green); }}
        .btn-rejected {{ background: var(--red); }}
        .btn-needs-edit {{ background: var(--amber); }}
        .detail-title-row {{ display: flex; align-items: start; justify-content: space-between; gap: 16px; }}
        .detail-grid {{ display: grid; grid-template-columns: minmax(0, 420px) minmax(0, 1fr); gap: 16px; }}
        .video-panel, .review-panel, .file-section, .timeline-section {{ padding: 18px; }}
        video {{ width: min(360px, 100%); aspect-ratio: 9 / 16; background: #05070a; border-radius: 10px; display: block; }}
        audio {{ width: min(360px, 100%); display: block; margin-bottom: 12px; }}
        .download-link {{ margin-top: 12px; width: min(360px, 100%); }}
        pre {{ margin: 0; white-space: pre-wrap; overflow-wrap: anywhere; background: #05070a; color: #dce8f7; border: 1px solid #182638; padding: 14px; border-radius: 10px; }}
        .tts-integrity {{ margin: 0 0 12px; padding: 12px; border: 1px solid var(--line); border-radius: 10px; background: #0b111a; }}
        .tts-integrity dl {{ display: grid; grid-template-columns: 140px minmax(0, 1fr); gap: 8px 10px; margin: 10px 0 0; }}
        .tts-integrity dt {{ color: var(--muted); font-size: 12px; }}
        .tts-integrity dd {{ margin: 0; overflow-wrap: anywhere; font-family: Consolas, monospace; font-size: 12px; color: #dce8f7; }}
        .missing, .empty {{ padding: 24px; border: 1px dashed var(--line); color: var(--muted); border-radius: 10px; background: #0b111a; }}
        .warning {{ padding: 12px; margin: 0 0 12px; border: 1px solid color-mix(in srgb, var(--amber), transparent 35%); background: color-mix(in srgb, var(--amber), transparent 88%); color: var(--amber); border-radius: 10px; }}
        .visual-warning {{ padding: 14px; margin: 0 0 12px; border: 1px solid color-mix(in srgb, var(--red), transparent 28%); background: color-mix(in srgb, var(--red), transparent 88%); color: #ffb5bd; border-radius: 10px; font-weight: 800; letter-spacing: .08em; }}
        .section-title-row {{ display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 14px; }}
        .timeline-grid {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }}
        .scene-card {{ overflow: hidden; background: var(--panel-2); }}
        .scene-image, .scene-missing {{ width: 100%; aspect-ratio: 9 / 16; object-fit: cover; display: block; background: #05070a; }}
        .scene-missing {{ display: grid; place-items: center; color: var(--muted); }}
        .scene-body {{ padding: 12px; }}
        .scene-body p {{ margin: 8px 0 0; color: #cbd8e8; font-size: 13px; line-height: 1.35; }}
        .scene-meta {{ display: flex; gap: 6px; flex-wrap: wrap; color: var(--muted); font-size: 12px; }}
        @media (max-width: 900px) {{ .summary, .cards, .detail-grid, .score-strip, .timeline-grid {{ grid-template-columns: 1fr; }} .card {{ grid-template-columns: 88px minmax(0, 1fr); }} .thumb {{ min-height: 170px; }} .controls {{ align-items: stretch; flex-direction: column; }} }}
      </style>
    </head>
    <body>{body}</body>
    </html>
    """


def _safe_video_dir(output_dir: Path, value: str) -> Path | None:
    path = (output_dir / value).resolve()
    if not str(path).startswith(str(output_dir)) or not (path / "video-plan.json").exists():
        return None
    return path


def _safe_media_path(output_dir: Path, value: str) -> Path | None:
    path = (output_dir / value).resolve()
    if not str(path).startswith(str(output_dir)) or not path.exists():
        return None
    return path


def _thumbnail_html(output_dir: Path, video_dir: Path) -> str:
    for name in ["thumbnail.jpg", "preview-thumbnail.jpg"]:
        path = video_dir / name
        if path.exists():
            media_url = "/media?path=" + urllib.parse.quote(str(path.relative_to(output_dir)))
            return f'<img class="thumb" src="{media_url}" alt="thumbnail">'
    return '<div class="thumb"></div>'


def _video_html(output_dir: Path, path: Path, missing_text: str) -> str:
    if not path.exists():
        return f'<div class="missing">{_e(missing_text)}</div>'
    media_url = _media_url(output_dir, path, cache_bust=True)
    poster = ""
    poster_path = path.parent / ("preview-thumbnail.jpg" if path.name == "preview.mp4" else "thumbnail.jpg")
    if poster_path.exists():
        poster_url = _media_url(output_dir, poster_path, cache_bust=True)
        poster = f' poster="{poster_url}"'
    return f'<video controls preload="metadata"{poster} src="{media_url}"></video>'


def _audio_html(output_dir: Path, path: Path) -> str:
    if not path.exists():
        return '<div class="missing">voiceover.mp3 missing. Use Generate Voiceover after configuring TTS, or run mock mode to verify the workflow.</div>'
    media_url = _media_url(output_dir, path)
    return f'<audio controls preload="metadata" src="{media_url}"></audio>'


def _download_link(output_dir: Path, path: Path) -> str:
    if not path.exists():
        return ""
    media_url = _media_url(output_dir, path) + "&download=1"
    return f'<a class="download-link" href="{media_url}">Download final.mp4</a>'


def _media_url(output_dir: Path, path: Path, cache_bust: bool = False) -> str:
    url = "/media?path=" + urllib.parse.quote(str(path.relative_to(output_dir)))
    if cache_bust:
        url += "&v=" + str(int(path.stat().st_mtime))
    return url


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _dashboard_tts_provider() -> str:
    return os.getenv("TTS_PROVIDER", "auto").lower()


def slug(value: str) -> str:
    return value.lower().replace(" ", "-")


def _e(value: object) -> str:
    return html.escape(str(value), quote=True)
