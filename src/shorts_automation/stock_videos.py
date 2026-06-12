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
USER_AGENT = "MasyraShorts/0.1 (+https://masyralabs.com)"


class StockVideoError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        provider: str,
        url: str | None = None,
        status_code: int | None = None,
        response_body: str | None = None,
    ) -> None:
        super().__init__(message)
        self.provider = provider
        self.url = url
        self.status_code = status_code
        self.response_body = response_body

    def to_dict(self) -> dict:
        return {
            "provider": self.provider,
            "url": self.url,
            "status_code": self.status_code,
            "response_body": self.response_body,
            "message": str(self),
        }


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
        request = self.build_search_request(f"https://api.pexels.com/videos/search?{params}")
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise _http_error(self.name, request.full_url, exc) from exc
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

    def build_search_request(self, url: str) -> urllib.request.Request:
        return urllib.request.Request(
            url,
            headers={
                "Authorization": self.api_key,
                "User-Agent": USER_AGENT,
                "Accept": "application/json",
            },
        )


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
        request = self.build_search_request(f"https://pixabay.com/api/videos/?{params}")
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise _http_error(self.name, request.full_url, exc) from exc
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
                    "page_url": video.get("pageURL"),
                    "download_url": file.get("url"),
                    "width": file.get("width"),
                    "height": file.get("height"),
                    "duration": video.get("duration"),
                    "credit": video.get("user"),
                    "credit_url": f"https://pixabay.com/users/{video.get('user')}-{video.get('user_id')}/" if video.get("user") else None,
                    "source_metadata": {
                        "pageURL": video.get("pageURL"),
                        "type": video.get("type"),
                        "tags": video.get("tags"),
                        "user": video.get("user"),
                        "user_id": video.get("user_id"),
                    },
                }
            )
        return clips

    def build_search_request(self, url: str) -> urllib.request.Request:
        return urllib.request.Request(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "application/json",
                "Referer": "https://pixabay.com/",
            },
        )


def generate_video_clips_for_package(video_dir: Path, provider_name: str = "auto", force: bool = False, debug: bool = False) -> dict:
    video_dir = video_dir.resolve()
    prompts_path = video_dir / "asset-prompts.json"
    plan_path = video_dir / "video-plan.json"
    if not prompts_path.exists() or not plan_path.exists():
        result = {"video_dir": str(video_dir), "downloaded": 0, "warning": "asset-prompts.json or video-plan.json not found."}
        return _write_clip_result(video_dir, result)

    prompts = _read_json(prompts_path)
    plan = _read_json(plan_path)
    queries = build_clip_queries(plan, prompts)
    clips_dir = video_dir / "video-clips"
    clips_dir.mkdir(parents=True, exist_ok=True)
    providers = select_video_providers(provider_name)

    if not providers:
        result = {
            "video_dir": str(video_dir),
            "provider": provider_name,
            "downloaded": 0,
            "clip_count": 0,
            "publish_ready": False,
            "warning": "No stock video provider is configured. Falling back to OpenAI images only.",
            "warnings": ["No stock video provider is configured. Falling back to OpenAI images only."],
            "fallback": "openai_images",
            "queries": queries,
            "clips": [],
            "debug": debug,
        }
        _write_clip_manifest(video_dir, result)
        return _write_clip_result(video_dir, result)

    if not any(_provider_available(provider) for provider in providers):
        provider_names = [provider.name for provider in providers]
        result = {
            "video_dir": str(video_dir),
            "provider": provider_names[0] if provider_names else provider_name,
            "providers_attempted": provider_names,
            "downloaded": 0,
            "clip_count": 0,
            "publish_ready": False,
            "warning": "No configured stock video API key is available. Falling back to OpenAI images only.",
            "warnings": [_missing_key_warning(provider.name) for provider in providers],
            "fallback": "openai_images",
            "queries": queries,
            "clips": [],
            "debug": debug,
        }
        _write_clip_manifest(video_dir, result)
        return _write_clip_result(video_dir, result)

    clips = []
    warnings = []
    errors = []
    seen_urls = set()
    providers_attempted = []
    provider_used = None
    for provider in providers:
        if not _provider_available(provider):
            warnings.append(_missing_key_warning(provider.name))
            continue
        providers_attempted.append(provider.name)
        provider_clip_count = len(clips)
        for query in queries:
            try:
                candidates = provider.search(query, per_page=6)
            except (RuntimeError, urllib.error.URLError, StockVideoError, TimeoutError) as exc:
                warnings.append(_format_provider_failure(provider.name, "search", query, exc))
                if isinstance(exc, StockVideoError):
                    errors.append(exc.to_dict())
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
                        _download(download_url, output_path, provider=provider.name, referer=candidate.get("page_url") or candidate.get("url"))
                        clips.append({**candidate, "file": output_path.relative_to(video_dir).as_posix(), "query": query})
                    except (urllib.error.URLError, StockVideoError, TimeoutError, OSError) as exc:
                        warnings.append(_format_provider_failure(provider.name, "download", query, exc, url=download_url))
                        if isinstance(exc, StockVideoError):
                            errors.append(exc.to_dict())
                if len(clips) >= MAX_CLIPS:
                    break
            if len(clips) >= MAX_CLIPS:
                break
        if len(clips) >= MAX_CLIPS:
            break
        if len(clips) > provider_clip_count:
            provider_used = provider.name
            break
        if provider.name == "pexels" and any(next_provider.name == "pixabay" and _provider_available(next_provider) for next_provider in providers):
            warnings.append("Pexels failed to download usable clips; falling back to Pixabay.")

    downloaded_count = len([clip for clip in clips if not clip.get("skipped") and (video_dir / clip.get("file", "")).exists()])
    clip_file_count = len([clip for clip in clips if (video_dir / clip.get("file", "")).exists()])
    result = {
        "video_dir": str(video_dir),
        "provider": provider_used or (clips[0].get("provider") if clips else providers_attempted[-1] if providers_attempted else providers[0].name),
        "providers_attempted": providers_attempted,
        "downloaded": downloaded_count,
        "clip_count": len(clips),
        "real_clip_count": clip_file_count,
        "publish_ready": clip_file_count >= MIN_CLIPS,
        "fallback": None if clip_file_count >= MIN_CLIPS else "openai_images",
        "queries": queries,
        "clips": clips,
        "warnings": warnings,
        "errors": errors if debug else _summarize_errors(errors),
        "attribution_required": True,
        "debug": debug,
    }
    _write_clip_manifest(video_dir, result)
    return _write_clip_result(video_dir, result)


def generate_video_clips_for_dirs(video_dirs: list[Path], provider_name: str = "auto", force: bool = False, debug: bool = False) -> dict:
    results = [generate_video_clips_for_package(path, provider_name=provider_name, force=force, debug=debug) for path in video_dirs]
    return {
        "attempted": len(video_dirs),
        "packages_with_clips": sum(1 for result in results if result.get("real_clip_count", 0) >= MIN_CLIPS),
        "downloaded_count": sum(result.get("downloaded", 0) for result in results),
        "warnings": [warning for result in results for warning in result.get("warnings", [])],
        "results": results,
    }


def load_clip_manifest(video_dir: Path) -> dict:
    path = video_dir / "video-clips-manifest.json"
    return _read_json(path) if path.exists() else {}


def load_clip_result(video_dir: Path) -> dict:
    path = video_dir / "video-clips-result.json"
    return _read_json(path) if path.exists() else {}


def video_clips_available(video_dir: Path) -> bool:
    result = load_clip_result(video_dir)
    if result:
        return int(result.get("real_clip_count", 0) or 0) >= MIN_CLIPS
    manifest = load_clip_manifest(video_dir)
    clips = manifest.get("clips", [])
    return len([clip for clip in clips if (video_dir / clip.get("file", "")).exists()]) >= MIN_CLIPS


def default_video_provider() -> str:
    return os.getenv("VIDEO_PROVIDER", "auto")


def build_clip_queries(plan: dict, prompts: dict) -> list[str]:
    title = plan.get("trend", {}).get("title") or plan.get("title", "")
    category = plan.get("trend", {}).get("category", "")
    queries = category_clip_queries(category)
    if title:
        clean_title = _sanitize_query(title)
        if clean_title:
            queries.append(f"{clean_title} reaction")
    for scene in prompts.get("scenes", []):
        for search_query in scene.get("search_queries", []):
            cleaned = _sanitize_query(str(search_query))
            if cleaned:
                queries.append(cleaned)
        prompt = str(scene.get("prompt", ""))
        words = [word.strip(".,:;!?()[]'\"").lower() for word in prompt.split()]
        keywords = [word for word in words if len(word) > 4 and word not in _query_stopwords()]
        if keywords:
            queries.append(" ".join(keywords[:4]))
    unique = []
    for query in queries:
        query = " ".join(query.split())[:90]
        if query and query not in unique:
            unique.append(query)
    return unique[:MAX_CLIPS]


def category_clip_queries(category: str) -> list[str]:
    mapping = {
        "funny animals": ["cat reaction", "pet surprise", "funny animal"],
        "funny kids": ["funny reaction", "people surprised"],
        "funny fails": ["funny fail", "people surprised"],
        "reddit stories": ["phone text drama", "people surprised"],
        "sports drama": ["sports celebration", "crowd cheering"],
        "relationship stories": ["text message reaction", "couple argument"],
        "minecraft stories": ["gaming setup", "minecraft cave"],
        "motivational stories": ["person training", "emotional success"],
        "celebrity drama": ["red carpet cameras", "paparazzi flash"],
        "survival stories": ["wilderness survival", "rescue helicopter"],
        "crazy facts": ["amazing animal", "science experiment"],
        "viral news": ["breaking news reaction", "people surprised"],
        "ai": ["viral technology", "people surprised"],
        "sports": ["sports celebration", "people surprised"],
        "animals": ["cute animals", "funny reaction"],
        "horror stories": ["scary dark hallway", "people surprised"],
        "gaming": ["gaming setup", "funny reaction"],
        "celebrity": ["people surprised", "breaking news reaction"],
        "movies & tv": ["people surprised", "funny reaction"],
        "misc viral": ["funny reaction", "people surprised"],
    }
    return mapping.get(str(category).strip().lower(), ["funny reaction", "people surprised", "viral technology"])


def select_video_providers(provider_name: str) -> list[StockVideoProvider]:
    provider_name = (provider_name or "auto").lower()
    if provider_name == "pexels":
        providers: list[StockVideoProvider] = [PexelsVideoProvider()]
        pixabay = PixabayVideoProvider()
        if pixabay.available():
            providers.append(pixabay)
        return providers
    if provider_name == "pixabay":
        return [PixabayVideoProvider()]
    if provider_name in {"off", "none"}:
        return [OffVideoProvider()]
    pexels = PexelsVideoProvider()
    pixabay = PixabayVideoProvider()
    if pexels.available():
        return [pexels, pixabay]
    return [pixabay]


def select_video_provider(provider_name: str) -> StockVideoProvider:
    return select_video_providers(provider_name)[0]


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


def _download(url: str, output_path: Path, *, provider: str, referer: str | None = None) -> None:
    headers = {"User-Agent": USER_AGENT}
    if provider == "pixabay":
        headers["Referer"] = referer or "https://pixabay.com/"
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            output_path.write_bytes(response.read())
    except urllib.error.HTTPError as exc:
        raise _http_error(provider, url, exc) from exc


def _write_clip_manifest(video_dir: Path, result: dict) -> None:
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "provider": result.get("provider"),
        "clip_count": result.get("clip_count", 0),
        "real_clip_count": result.get("real_clip_count", 0),
        "publish_ready": result.get("publish_ready", False),
        "fallback": result.get("fallback"),
        "queries": result.get("queries", []),
        "clips": result.get("clips", []),
        "warnings": result.get("warnings", []),
        "errors": result.get("errors", []),
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


def _http_error(provider: str, url: str, exc: urllib.error.HTTPError) -> StockVideoError:
    body = exc.read().decode("utf-8", errors="replace")
    return StockVideoError(
        f"{provider} HTTP {exc.code} for {url}: {body}",
        provider=provider,
        url=url,
        status_code=exc.code,
        response_body=body,
    )


def _format_provider_failure(provider: str, operation: str, query: str, exc: BaseException, url: str | None = None) -> str:
    if isinstance(exc, StockVideoError):
        return f"{provider} {operation} failed for '{query}' with HTTP {exc.status_code} at {exc.url}: {exc.response_body}"
    location = f" at {url}" if url else ""
    return f"{provider} {operation} failed for '{query}'{location}: {exc}"


def _summarize_errors(errors: list[dict]) -> list[dict]:
    return [
        {
            "provider": error.get("provider"),
            "url": error.get("url"),
            "status_code": error.get("status_code"),
            "message": error.get("message"),
        }
        for error in errors
    ]


def _sanitize_query(value: str) -> str:
    words = [word.strip(".,:;!?()[]'\"").lower() for word in str(value).split()]
    return " ".join(word for word in words if word and word not in _query_stopwords())


def _query_stopwords() -> set[str]:
    return {
        "analysis",
        "brand",
        "clean",
        "copyrighted",
        "generated",
        "labs",
        "masyra",
        "moment",
        "original",
        "question",
        "short",
        "sleek",
        "trend",
        "vertical",
        "viral",
        "visual",
        "video",
    }
