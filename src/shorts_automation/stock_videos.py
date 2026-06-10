from __future__ import annotations

import json
import os
import shutil
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


MIN_CLIPS = 3
MAX_CLIPS = 8


class StockVideoProvider:
    name = "base"

    def search(self, query: str, *, per_page: int = 5) -> list[dict]:
        raise NotImplementedError


class OffVideoProvider(StockVideoProvider):
    name = "off"

    def available(self) -> bool:
        return False

    def search(self, query: str, *, per_page: int = 5) -> list[dict]:
        return []


class PexelsVideoProvider(StockVideoProvider):
    name = "pexels"

    def __init__(self) -> None:
        self.api_key = os.getenv("PEXELS_API_KEY", "")

    def available(self) -> bool:
        return bool(self.api_key)

    def search(self, query: str, *, per_page: int = 5) -> list[dict]:
        if not self.available():
            raise RuntimeError("PEXELS_API_KEY is missing.")
        params = urllib.parse.urlencode({"query": query, "orientation": "portrait", "per_page": per_page})
        request = urllib.request.Request(
            f"https://api.pexels.com/v1/videos/search?{params}",
            headers={"Authorization": self.api_key},
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            data = json.loads(response.read().decode("utf-8"))
        clips = []
        for video in data.get("videos", []):
            file = _best_pexels_file(video.get("video_files", []))
            if not file:
                continue
            clips.append(
                {
                    "provider": self.name,
                    "id": video.get("id"),
                    "url": video.get("url"),
                    "download_url": file["link"],
                    "width": file.get("width"),
                    "height": file.get("height"),
                    "duration": video.get("duration"),
                    "credit": video.get("user", {}).get("name"),
                    "credit_url": video.get("user", {}).get("url"),
                }
            )
        return clips


class PixabayVideoProvider(StockVideoProvider):
    name = "pixabay"

    def __init__(self) -> None:
        self.api_key = os.getenv("PIXABAY_API_KEY", "")

    def available(self) -> bool:
        return bool(self.api_key)

    def search(self, query: str, *, per_page: int = 5) -> list[dict]:
        if not self.available():
            raise RuntimeError("PIXABAY_API_KEY is missing.")
        params = urllib.parse.urlencode(
            {
                "key": self.api_key,
                "q": query,
                "video_type": "film",
                "orientation": "vertical",
                "per_page": per_page,
                "safesearch": "true",
            }
        )
        with urllib.request.urlopen(f"https://pixabay.com/api/videos/?{params}", timeout=60) as response:
            data = json.loads(response.read().decode("utf-8"))
        clips = []
        for video in data.get("hits", []):
            file = _best_pixabay_file(video.get("videos", {}))
            if not file:
                continue
            clips.append(
                {
                    "provider": self.name,
                    "id": video.get("id"),
                    "url": video.get("pageURL"),
                    "download_url": file.get("url"),
                    "width": file.get("width"),
                    "height": file.get("height"),
                    "duration": video.get("duration"),
                    "credit": video.get("user"),
                    "credit_url": f"https://pixabay.com/users/{video.get('user')}-{video.get('user_id')}/" if video.get("user") else None,
                }
            )
        return clips


def generate_video_clips_for_package(video_dir: Path, provider_name: str = "auto", force: bool = False) -> dict:
    video_dir = video_dir.resolve()
    prompts_path = video_dir / "asset-prompts.json"
    plan_path = video_dir / "video-plan.json"
    if not prompts_path.exists() or not plan_path.exists():
        result = {"video_dir": str(video_dir), "downloaded": 0, "warning": "asset-prompts.json or video-plan.json not found."}
        return _write_clip_result(video_dir, result)

    prompts = _read_json(prompts_path)
    plan = _read_json(plan_path)
    queries = build_clip_queries(plan, prompts)
    provider = select_video_provider(provider_name)
    clips_dir = video_dir / "video-clips"
    clips_dir.mkdir(parents=True, exist_ok=True)

    if not _provider_available(provider):
        result = {
            "video_dir": str(video_dir),
            "provider": provider.name,
            "downloaded": 0,
            "publish_ready": False,
            "warning": _missing_key_warning(provider.name),
            "queries": queries,
            "clips": [],
        }
        _write_clip_manifest(video_dir, result)
        return _write_clip_result(video_dir, result)

    clips = []
    warnings = []
    seen_urls = set()
    for query in queries:
        try:
            candidates = provider.search(query, per_page=6)
        except (RuntimeError, urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
            warnings.append(f"{provider.name} search failed for '{query}': {exc}")
            continue
        for candidate in candidates:
            download_url = candidate.get("download_url")
            if not download_url or download_url in seen_urls:
                continue
            seen_urls.add(download_url)
            clip_index = len(clips) + 1
            output_path = clips_dir / f"clip-{clip_index:02d}.mp4"
            if output_path.exists() and not force:
                clips.append({**candidate, "file": output_path.relative_to(video_dir).as_posix(), "query": query, "skipped": True})
            else:
                try:
                    _download(download_url, output_path)
                    clips.append({**candidate, "file": output_path.relative_to(video_dir).as_posix(), "query": query})
                except (urllib.error.URLError, TimeoutError, OSError) as exc:
                    warnings.append(f"Download failed for '{query}': {exc}")
            if len(clips) >= MAX_CLIPS:
                break
        if len(clips) >= MAX_CLIPS:
            break

    result = {
        "video_dir": str(video_dir),
        "provider": provider.name,
        "downloaded": len([clip for clip in clips if not clip.get("skipped")]),
        "clip_count": len(clips),
        "publish_ready": len(clips) >= MIN_CLIPS,
        "queries": queries,
        "clips": clips,
        "warnings": warnings,
        "attribution_required": True,
    }
    _write_clip_manifest(video_dir, result)
    return _write_clip_result(video_dir, result)


def generate_video_clips_for_dirs(video_dirs: list[Path], provider_name: str = "auto", force: bool = False) -> dict:
    results = [generate_video_clips_for_package(path, provider_name=provider_name, force=force) for path in video_dirs]
    return {
        "attempted": len(video_dirs),
        "packages_with_clips": sum(1 for result in results if result.get("clip_count", 0) >= MIN_CLIPS),
        "downloaded_count": sum(result.get("downloaded", 0) for result in results),
        "warnings": [warning for result in results for warning in result.get("warnings", [])],
        "results": results,
    }


def load_clip_manifest(video_dir: Path) -> dict:
    path = video_dir / "video-clips-manifest.json"
    return _read_json(path) if path.exists() else {}


def video_clips_available(video_dir: Path) -> bool:
    manifest = load_clip_manifest(video_dir)
    clips = manifest.get("clips", [])
    return len([clip for clip in clips if (video_dir / clip.get("file", "")).exists()]) >= MIN_CLIPS


def default_video_provider() -> str:
    return os.getenv("VIDEO_PROVIDER", "auto")


def build_clip_queries(plan: dict, prompts: dict) -> list[str]:
    title = plan.get("trend", {}).get("title") or plan.get("title", "")
    category = plan.get("trend", {}).get("category", "")
    queries = [
        f"{category} people emotion vertical",
        f"{title} reaction",
        f"{category} action movement",
    ]
    for scene in prompts.get("scenes", []):
        prompt = str(scene.get("prompt", ""))
        words = [word.strip(".,:;!?()[]'\"").lower() for word in prompt.split()]
        keywords = [word for word in words if len(word) > 4 and word not in {"original", "vertical", "visual", "trend", "copyrighted"}]
        if keywords:
            queries.append(" ".join(keywords[:4]))
    unique = []
    for query in queries:
        query = " ".join(query.split())[:90]
        if query and query not in unique:
            unique.append(query)
    return unique[:MAX_CLIPS]


def select_video_provider(provider_name: str) -> StockVideoProvider:
    provider_name = (provider_name or "auto").lower()
    if provider_name == "pexels":
        return PexelsVideoProvider()
    if provider_name == "pixabay":
        return PixabayVideoProvider()
    if provider_name in {"off", "none"}:
        return OffVideoProvider()
    pexels = PexelsVideoProvider()
    if pexels.available():
        return pexels
    return PixabayVideoProvider()


def _provider_available(provider: StockVideoProvider) -> bool:
    return bool(getattr(provider, "available")())


def _missing_key_warning(provider_name: str) -> str:
    if provider_name == "pexels":
        return "PEXELS_API_KEY is missing; stock video clips were not downloaded."
    if provider_name == "pixabay":
        return "PIXABAY_API_KEY is missing; stock video clips were not downloaded."
    if provider_name == "off":
        return "VIDEO_PROVIDER is off; stock video clips were not downloaded."
    return "Stock video provider is not configured."


def _best_pexels_file(files: list[dict]) -> dict | None:
    mp4_files = [file for file in files if file.get("file_type") == "video/mp4" and file.get("link")]
    if not mp4_files:
        return None
    mp4_files.sort(key=lambda file: ((file.get("height", 0) > file.get("width", 0)), file.get("height", 0)), reverse=True)
    return mp4_files[0]


def _best_pixabay_file(files: dict) -> dict | None:
    options = [files.get(name) for name in ["large", "medium", "small", "tiny"] if files.get(name)]
    options = [option for option in options if option.get("url")]
    if not options:
        return None
    options.sort(key=lambda file: ((file.get("height", 0) > file.get("width", 0)), file.get("height", 0)), reverse=True)
    return options[0]


def _download(url: str, output_path: Path) -> None:
    with urllib.request.urlopen(url, timeout=180) as response:
        output_path.write_bytes(response.read())


def _write_clip_manifest(video_dir: Path, result: dict) -> None:
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "provider": result.get("provider"),
        "clip_count": result.get("clip_count", 0),
        "publish_ready": result.get("publish_ready", False),
        "queries": result.get("queries", []),
        "clips": result.get("clips", []),
        "warnings": result.get("warnings", []),
        "attribution_required": result.get("attribution_required", True),
    }
    (video_dir / "video-clips-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_clip_result(video_dir: Path, result: dict) -> dict:
    result = {"generated_at": datetime.now(timezone.utc).isoformat(), **result}
    (video_dir / "video-clips-result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
