from __future__ import annotations

import html
import json
import mimetypes
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .status_store import DEFAULT_STATUS, StatusStore, VALID_STATUSES


def serve_dashboard(output_dir: Path, host: str = "127.0.0.1", port: int = 8765) -> None:
    output_dir = output_dir.resolve()
    store = StatusStore(output_dir / "review-status.json")

    class DashboardHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path == "/":
                self._send_html(render_index(output_dir, store))
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
                self._send_file(media_path)
                return
            self._send_text("Not found", status=404)

        def do_POST(self) -> None:
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path != "/status":
                self._send_text("Not found", status=404)
                return

            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length).decode("utf-8")
            params = urllib.parse.parse_qs(body)
            video_dir = _safe_video_dir(output_dir, params.get("dir", [""])[0])
            status = params.get("status", [DEFAULT_STATUS])[0]
            notes = params.get("notes", [""])[0]

            if not video_dir or status not in VALID_STATUSES:
                self._send_text("Invalid status update", status=400)
                return

            store.set(video_dir, status=status, notes=notes)
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

        def _send_file(self, path: Path) -> None:
            content_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.end_headers()
            self.wfile.write(path.read_bytes())

    server = ThreadingHTTPServer((host, port), DashboardHandler)
    print(f"Dashboard: http://{host}:{port}")
    server.serve_forever()


def render_index(output_dir: Path, store: StatusStore) -> str:
    packages = find_video_packages(output_dir)
    rows = []
    for video_dir in packages:
        plan = _read_json(video_dir / "video-plan.json")
        trend = plan.get("trend", {})
        scores = plan.get("scores", {})
        status = store.get(video_dir)["status"]
        detail_url = "/video?dir=" + urllib.parse.quote(str(video_dir.relative_to(output_dir)))
        rows.append(
            f"""
            <tr>
              <td><a href="{detail_url}">{_e(trend.get("title", video_dir.name))}</a></td>
              <td>{_e(trend.get("category", ""))}</td>
              <td>{_e(status)}</td>
              <td>{scores.get("trend_score", "")}</td>
              <td>{scores.get("growth_score", "")}</td>
              <td>{scores.get("competition_score", "")}</td>
              <td>{scores.get("viral_potential_score", "")}</td>
            </tr>
            """
        )

    return page(
        "Masyra Labs Review Dashboard",
        f"""
        <section class="toolbar">
          <div>
            <h1>Masyra Labs Review Dashboard</h1>
            <p>{len(packages)} video packages found under {_e(str(output_dir))}</p>
          </div>
        </section>
        <table>
          <thead>
            <tr><th>Trend</th><th>Category</th><th>Status</th><th>Trend</th><th>Growth</th><th>Competition</th><th>Viral</th></tr>
          </thead>
          <tbody>{''.join(rows)}</tbody>
        </table>
        """,
    )


def render_video_detail(output_dir: Path, store: StatusStore, video_dir: Path) -> str:
    plan = _read_json(video_dir / "video-plan.json")
    upload = _read_json(video_dir / "upload-metadata.json")
    checklist = _read_json(video_dir / "copyright-checklist.json")
    prompts = _read_json(video_dir / "asset-prompts.json")
    status_data = store.get(video_dir)
    final_mp4 = video_dir / "final.mp4"
    voiceover_mp3 = video_dir / "voiceover.mp3"
    rel = str(video_dir.relative_to(output_dir))
    final_media = ""
    if final_mp4.exists():
        media_url = "/media?path=" + urllib.parse.quote(str(final_mp4.relative_to(output_dir)))
        final_media = f'<video controls src="{media_url}"></video>'
    else:
        final_media = '<div class="missing">No final.mp4 yet</div>'

    return page(
        plan.get("title", "Video package"),
        f"""
        <a href="/">Back to dashboard</a>
        <h1>{_e(plan.get("title", video_dir.name))}</h1>
        <div class="grid">
          <section>
            <h2>Trend</h2>
            <p><b>Title:</b> {_e(plan.get("trend", {}).get("title", ""))}</p>
            <p><b>Category:</b> {_e(plan.get("trend", {}).get("category", ""))}</p>
            <pre>{_e(json.dumps(plan.get("scores", {}), ensure_ascii=False, indent=2))}</pre>
          </section>
          <section>
            <h2>Review</h2>
            <form method="post" action="/status">
              <input type="hidden" name="dir" value="{_e(rel)}">
              <select name="status">
                {status_options(status_data["status"])}
              </select>
              <textarea name="notes" placeholder="Review notes">{_e(status_data.get("notes", ""))}</textarea>
              <button type="submit">Save Status</button>
            </form>
          </section>
        </div>
        <section><h2>Final MP4</h2>{final_media}</section>
        <section><h2>Script</h2><pre>{_e(_read_text(video_dir / "script.txt"))}</pre></section>
        <section><h2>Subtitles</h2><pre>{_e(_read_text(video_dir / "subtitles.srt"))}</pre></section>
        <section><h2>Render Brief</h2><pre>{_e(_read_text(video_dir / "render-brief.txt"))}</pre></section>
        <section><h2>Upload Metadata</h2><pre>{_e(json.dumps(upload, ensure_ascii=False, indent=2))}</pre></section>
        <section><h2>Asset Prompts</h2><pre>{_e(json.dumps(prompts, ensure_ascii=False, indent=2))}</pre></section>
        <section><h2>Copyright Safety Checklist</h2><pre>{_e(json.dumps(checklist, ensure_ascii=False, indent=2))}</pre></section>
        <section><h2>Voiceover</h2><p>{'voiceover.mp3 exists' if voiceover_mp3.exists() else 'No voiceover.mp3 yet; using voiceover.txt only.'}</p><pre>{_e(_read_text(video_dir / "voiceover.txt"))}</pre></section>
        """,
    )


def status_options(current: str) -> str:
    return "".join(
        f'<option value="{_e(status)}" {"selected" if status == current else ""}>{_e(status)}</option>'
        for status in ["Needs Edit", "Approved", "Rejected"]
    )


def find_video_packages(output_dir: Path) -> list[Path]:
    return sorted(output_dir.glob("*/videos/*"), reverse=True)


def page(title: str, body: str) -> str:
    return f"""
    <!doctype html>
    <html>
    <head>
      <meta charset="utf-8">
      <meta name="viewport" content="width=device-width, initial-scale=1">
      <title>{_e(title)}</title>
      <style>
        body {{ margin: 0; font-family: Segoe UI, Arial, sans-serif; background: #f6f7f9; color: #18212f; }}
        h1 {{ font-size: 28px; margin: 0 0 10px; }}
        h2 {{ font-size: 18px; margin: 0 0 12px; }}
        a {{ color: #0b5cad; text-decoration: none; }}
        section, table {{ width: min(1180px, calc(100% - 32px)); margin: 18px auto; }}
        section {{ background: #fff; border: 1px solid #dce2ea; border-radius: 8px; padding: 18px; }}
        table {{ border-collapse: collapse; background: #fff; border: 1px solid #dce2ea; }}
        th, td {{ padding: 12px; border-bottom: 1px solid #e8edf3; text-align: left; vertical-align: top; }}
        th {{ background: #eff4f9; font-size: 13px; text-transform: uppercase; letter-spacing: .04em; }}
        pre {{ white-space: pre-wrap; overflow-wrap: anywhere; background: #0f1720; color: #e7edf5; padding: 14px; border-radius: 6px; }}
        .toolbar {{ display: flex; justify-content: space-between; align-items: center; background: transparent; border: 0; padding: 8px 0; }}
        .grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; width: min(1180px, calc(100% - 32px)); margin: 18px auto; }}
        .grid section {{ width: auto; margin: 0; }}
        select, textarea, button {{ width: 100%; box-sizing: border-box; font: inherit; margin-top: 10px; }}
        textarea {{ min-height: 100px; padding: 10px; }}
        select, button {{ padding: 10px 12px; }}
        button {{ background: #18212f; color: white; border: 0; border-radius: 6px; cursor: pointer; }}
        video {{ width: min(360px, 100%); aspect-ratio: 9 / 16; background: #111; }}
        .missing {{ padding: 28px; border: 1px dashed #b7c3d0; border-radius: 8px; color: #576575; }}
        @media (max-width: 800px) {{ .grid {{ grid-template-columns: 1fr; }} }}
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


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _e(value: object) -> str:
    return html.escape(str(value), quote=True)
