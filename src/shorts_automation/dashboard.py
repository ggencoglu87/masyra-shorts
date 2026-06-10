from __future__ import annotations

import html
import json
import mimetypes
import os
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .renderer import DEFAULT_DURATION_SECONDS, PREVIEW_DURATION_SECONDS, render_video_package
from .status_store import DEFAULT_STATUS, StatusStore, VALID_STATUSES
from .tts import synthesize_voiceover
from .visuals import generate_visuals_for_package, load_scene_manifest, visuals_available


STATUS_ORDER = ["Needs Edit", "Approved", "Rejected"]
SORT_OPTIONS = {
    "viral": ("Viral score", "viral_potential_score"),
    "trend": ("Trend score", "trend_score"),
    "growth": ("Growth score", "growth_score"),
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
                generate_visuals_for_package(video_dir, provider_name=params.get("provider", ["auto"])[0])
            elif action == "generate_tts":
                synthesize_voiceover(video_dir, provider_name=params.get("provider", [_dashboard_tts_provider()])[0], force=False)
            elif action == "rerender":
                render_video_package(video_dir, duration_seconds=PREVIEW_DURATION_SECONDS, preview=True)
                render_video_package(video_dir, duration_seconds=DEFAULT_DURATION_SECONDS, preview=False)
            elif action == "rerender_audio":
                synthesize_voiceover(video_dir, provider_name=params.get("provider", [_dashboard_tts_provider()])[0], force=False)
                render_video_package(video_dir, duration_seconds=PREVIEW_DURATION_SECONDS, preview=True)
                render_video_package(video_dir, duration_seconds=DEFAULT_DURATION_SECONDS, preview=False)
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
        if status_filter == "all" or package["status"] == status_filter
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
          {visual_badge(package["visuals_ready"])}
          {audio_badge(package["audio_ready"])}
        </div>
        <h2><a href="{detail_url}">{_e(package["trend_title"])}</a></h2>
        <div class="score-grid">
          {score_box("Viral", scores.get("viral_potential_score", ""))}
          {score_box("Trend", scores.get("trend_score", ""))}
          {score_box("Growth", scores.get("growth_score", ""))}
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
    manifest = load_scene_manifest(video_dir)
    status_data = store.get(video_dir)
    final_mp4 = video_dir / "final.mp4"
    preview_mp4 = video_dir / "preview.mp4"
    voiceover_mp3 = video_dir / "voiceover.mp3"
    tts_result = _read_json(video_dir / "tts-result.json")
    tts_provider = tts_result.get("provider", "not generated")
    rel = str(video_dir.relative_to(output_dir))
    download = _download_link(output_dir, final_mp4)
    visual_warning = ""
    if not visuals_available(video_dir):
        visual_warning = '<div class="visual-warning">VISUALS NOT GENERATED</div>'
    audio_warning = ""
    if (final_mp4.exists() or preview_mp4.exists()) and not voiceover_mp3.exists():
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
              <input type="hidden" name="action" value="generate_visuals">
              <input type="hidden" name="provider" value="auto">
              <button type="submit">Generate Visuals</button>
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
              <input type="hidden" name="action" value="rerender_audio">
              <input type="hidden" name="provider" value="{_e(_dashboard_tts_provider())}">
              <button type="submit">Re-render With Audio</button>
            </form>
            <h2>Quick Preview</h2>
            {_video_html(output_dir, preview_mp4, "No preview.mp4 yet")}
            <h2>Voiceover Audio</h2>
            <p class="muted">TTS provider: {_e(tts_provider)}</p>
            {_audio_html(output_dir, voiceover_mp3)}
          </div>
        </section>
        <section class="score-strip">
          {score_box("Viral", plan.get("scores", {}).get("viral_potential_score", ""))}
          {score_box("Trend", plan.get("scores", {}).get("trend_score", ""))}
          {score_box("Growth", plan.get("scores", {}).get("growth_score", ""))}
        {score_box("Competition", plan.get("scores", {}).get("competition_score", ""))}
        </section>
        {scene_timeline(output_dir, video_dir, manifest)}
        {file_section("script.txt", _read_text(video_dir / "script.txt"))}
        {file_section("voiceover.txt", _read_text(video_dir / "voiceover.txt"))}
        {file_section("tts-result.json", json.dumps(tts_result, ensure_ascii=False, indent=2))}
        {file_section("subtitles.srt", _read_text(video_dir / "subtitles.srt"))}
        {file_section("upload-metadata.json", json.dumps(upload, ensure_ascii=False, indent=2))}
        {file_section("render-brief.txt", _read_text(video_dir / "render-brief.txt"))}
        {file_section("asset-prompts.json", json.dumps(prompts, ensure_ascii=False, indent=2))}
        """,
    )


def build_package_rows(output_dir: Path, store: StatusStore) -> list[dict]:
    rows = []
    for video_dir in find_video_packages(output_dir):
        plan = _read_json(video_dir / "video-plan.json")
        status = store.get(video_dir)["status"]
        rows.append(
            {
                "video_dir": video_dir,
                "status": status,
                "trend_title": plan.get("trend", {}).get("title", video_dir.name),
                "category": plan.get("trend", {}).get("category", ""),
                "scores": plan.get("scores", {}),
                "visuals_ready": visuals_available(video_dir),
                "audio_ready": (video_dir / "voiceover.mp3").exists(),
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


def visual_badge(ready: bool) -> str:
    if ready:
        return '<span class="pill status-approved">Visuals Ready</span>'
    return '<span class="pill status-rejected">VISUALS NOT GENERATED</span>'


def audio_badge(ready: bool) -> str:
    if ready:
        return '<span class="pill status-approved">Voiceover Ready</span>'
    return '<span class="pill status-needs-edit">Voiceover Missing</span>'


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


def scene_timeline(output_dir: Path, video_dir: Path, manifest: dict) -> str:
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
      </div>
      <div class="timeline-grid">{''.join(cards)}</div>
    </section>
    """


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
    media_url = "/media?path=" + urllib.parse.quote(str(path.relative_to(output_dir)))
    poster = ""
    poster_path = path.parent / ("preview-thumbnail.jpg" if path.name == "preview.mp4" else "thumbnail.jpg")
    if poster_path.exists():
        poster_url = "/media?path=" + urllib.parse.quote(str(poster_path.relative_to(output_dir)))
        poster = f' poster="{poster_url}"'
    return f'<video controls preload="metadata"{poster} src="{media_url}"></video>'


def _audio_html(output_dir: Path, path: Path) -> str:
    if not path.exists():
        return '<div class="missing">voiceover.mp3 missing. Use Generate Voiceover after configuring TTS, or run mock mode to verify the workflow.</div>'
    media_url = "/media?path=" + urllib.parse.quote(str(path.relative_to(output_dir)))
    return f'<audio controls preload="metadata" src="{media_url}"></audio>'


def _download_link(output_dir: Path, path: Path) -> str:
    if not path.exists():
        return ""
    media_url = "/media?path=" + urllib.parse.quote(str(path.relative_to(output_dir))) + "&download=1"
    return f'<a class="download-link" href="{media_url}">Download final.mp4</a>'


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
    return os.getenv("TTS_PROVIDER", "elevenlabs").lower()


def slug(value: str) -> str:
    return value.lower().replace(" ", "-")


def _e(value: object) -> str:
    return html.escape(str(value), quote=True)
