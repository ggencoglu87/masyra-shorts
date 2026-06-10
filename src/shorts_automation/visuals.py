from __future__ import annotations

import base64
import json
import math
import os
import random
import shutil
import struct
import time
import urllib.error
import urllib.request
import zlib
from datetime import datetime, timezone
from pathlib import Path


MIN_SCENES = 4
MAX_SCENES = 6
PLACEHOLDER_WIDTH = 720
PLACEHOLDER_HEIGHT = 1280
SUPPORTED_OPENAI_IMAGE_SIZES = {"1024x1024", "1024x1536", "1536x1024"}


class OpenAIImageError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None, response_body: str | None = None, payload: dict | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body
        self.payload = payload or {}


class ImageProvider:
    name = "base"

    def generate(self, prompt: str, output_path: Path, *, seed: int) -> dict:
        raise NotImplementedError


class OpenAIImageProvider(ImageProvider):
    name = "openai"

    def __init__(self) -> None:
        self.api_key = os.getenv("OPENAI_API_KEY", "")
        self.model = os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-1")
        self.size = os.getenv("OPENAI_IMAGE_SIZE", "1024x1536")

    def available(self) -> bool:
        return bool(self.api_key)

    def generate(self, prompt: str, output_path: Path, *, seed: int) -> dict:
        if not self.available():
            raise OpenAIImageError("OPENAI_API_KEY is not configured.")
        if self.size not in SUPPORTED_OPENAI_IMAGE_SIZES:
            raise OpenAIImageError(
                f"Unsupported OPENAI_IMAGE_SIZE '{self.size}'. Supported sizes: {', '.join(sorted(SUPPORTED_OPENAI_IMAGE_SIZES))}.",
                payload=self.payload(prompt),
            )

        payload = self.payload(prompt)
        request = urllib.request.Request(
            "https://api.openai.com/v1/images/generations",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise OpenAIImageError(
                f"OpenAI Images API returned HTTP {exc.code}.",
                status_code=exc.code,
                response_body=body,
                payload=payload,
            ) from exc

        image = data.get("data", [{}])[0]
        if image.get("b64_json"):
            output_path.write_bytes(base64.b64decode(image["b64_json"]))
        elif image.get("url"):
            _download(image["url"], output_path)
        else:
            raise RuntimeError("OpenAI image response did not include image data.")

        return {"provider": self.name, "model": self.model, "size": self.size, "path": str(output_path)}

    def payload(self, prompt: str) -> dict:
        return {
            "model": self.model,
            "prompt": prompt,
            "size": self.size,
            "n": 1,
        }


class ReplicateImageProvider(ImageProvider):
    name = "replicate"

    def __init__(self) -> None:
        self.api_token = os.getenv("REPLICATE_API_TOKEN", "")
        self.version = os.getenv("REPLICATE_IMAGE_VERSION", "")

    def available(self) -> bool:
        return bool(self.api_token and self.version)

    def generate(self, prompt: str, output_path: Path, *, seed: int) -> dict:
        if not self.available():
            raise RuntimeError("REPLICATE_API_TOKEN and REPLICATE_IMAGE_VERSION are required.")

        payload = {
            "version": self.version,
            "input": {
                "prompt": prompt,
                "width": 768,
                "height": 1344,
                "num_outputs": 1,
            },
        }
        request = urllib.request.Request(
            "https://api.replicate.com/v1/predictions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Token {self.api_token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            prediction = json.loads(response.read().decode("utf-8"))

        get_url = prediction.get("urls", {}).get("get")
        if not get_url:
            raise RuntimeError("Replicate prediction did not include polling URL.")

        for _attempt in range(90):
            poll = urllib.request.Request(get_url, headers={"Authorization": f"Token {self.api_token}"})
            with urllib.request.urlopen(poll, timeout=30) as response:
                prediction = json.loads(response.read().decode("utf-8"))
            status = prediction.get("status")
            if status == "succeeded":
                output = prediction.get("output")
                image_url = output[0] if isinstance(output, list) else output
                if not image_url:
                    raise RuntimeError("Replicate succeeded without an output URL.")
                _download(str(image_url), output_path)
                return {"provider": self.name, "path": str(output_path)}
            if status in {"failed", "canceled"}:
                raise RuntimeError(f"Replicate prediction {status}.")
            time.sleep(2)

        raise RuntimeError("Replicate prediction timed out.")


class PlaceholderImageProvider(ImageProvider):
    name = "placeholder"

    def generate(self, prompt: str, output_path: Path, *, seed: int) -> dict:
        write_placeholder_png(output_path, prompt=prompt, seed=seed)
        return {"provider": self.name, "path": str(output_path)}


def generate_visuals_for_package(
    video_dir: Path,
    provider_name: str = "auto",
    force: bool = False,
    allow_placeholder: bool = False,
    debug: bool = False,
) -> dict:
    video_dir = video_dir.resolve()
    prompts_path = video_dir / "asset-prompts.json"
    if not prompts_path.exists():
        result = {"video_dir": str(video_dir), "generated": 0, "warning": "asset-prompts.json not found."}
        _write_scene_manifest(video_dir, provider_name, "missing_prompts", [], [result["warning"]], result)
        return _write_visual_result(video_dir, result)

    prompts = _read_json(prompts_path)
    scene_prompts = normalize_scene_prompts(prompts)
    provider = select_provider(provider_name)
    images_dir = video_dir / "scene-images"
    images_dir.mkdir(parents=True, exist_ok=True)

    if isinstance(provider, OpenAIImageProvider) and not provider.available():
        result = {
            "video_dir": str(video_dir),
            "generated": 0,
            "provider": "openai_failed",
            "provider_requested": provider_name,
            "real_visuals_ready": False,
            "publish_ready": False,
            "warning": "OPENAI_API_KEY is missing. OpenAI Images was not called and scene images were not generated.",
            "warnings": ["OPENAI_API_KEY is missing. OpenAI Images was not called and scene images were not generated."],
        }
        _write_scene_manifest(video_dir, provider_name, "openai_failed", [], result["warnings"], result)
        return _write_visual_result(video_dir, result)

    scenes = []
    warnings = []
    for index, scene in enumerate(scene_prompts, start=1):
        output_path = images_dir / f"scene-{index:02d}.png"
        if output_path.exists() and not force:
            warnings.append(f"Scene {index}: {output_path.name} already exists; use --force to overwrite.")
            used_provider = _existing_scene_provider(video_dir, index) or "existing"
            scenes.append(
                {
                    "scene": index,
                    "time": scene.get("time", ""),
                    "duration_seconds": scene_duration(index),
                    "prompt": scene["prompt"],
                    "image": output_path.relative_to(video_dir).as_posix(),
                    "provider": used_provider,
                    "skipped": True,
                }
            )
            continue
        try:
            result = provider.generate(scene["prompt"], output_path, seed=index)
            used_provider = result["provider"]
        except OpenAIImageError as exc:
            error_data = {
                "message": str(exc),
                "status_code": exc.status_code,
                "response_body": exc.response_body,
                "payload": exc.payload if debug else _redact_prompt_payload(exc.payload),
            }
            warning = f"Scene {index}: OpenAI failed. {exc}"
            warnings.append(warning)
            openai_error = {
                "video_dir": str(video_dir),
                "generated": 0,
                "provider": "openai_failed",
                "provider_requested": provider_name,
                "real_visuals_ready": False,
                "publish_ready": False,
                "warning": warning,
                "warnings": warnings,
                "openai_error": error_data,
                "debug": debug,
            }
            if allow_placeholder:
                PlaceholderImageProvider().generate(scene["prompt"], output_path, seed=index)
                scenes.append(
                    {
                        "scene": index,
                        "time": scene.get("time", ""),
                        "duration_seconds": scene_duration(index),
                        "prompt": scene["prompt"],
                        "image": output_path.relative_to(video_dir).as_posix(),
                        "provider": "placeholder",
                        "openai_error": error_data,
                    }
                )
                continue
            _write_scene_manifest(video_dir, provider_name, "openai_failed", [], warnings, openai_error)
            return _write_visual_result(video_dir, openai_error)
        except (RuntimeError, urllib.error.URLError, TimeoutError) as exc:
            if provider.name == "placeholder":
                raise
            warnings.append(f"Scene {index}: {provider.name} failed. No placeholder was generated. {exc}")
            continue

        scenes.append(
            {
                "scene": index,
                "time": scene.get("time", ""),
                "duration_seconds": scene_duration(index),
                "prompt": scene["prompt"],
                "image": output_path.relative_to(video_dir).as_posix(),
                "provider": used_provider,
            }
        )

    thumbnail_source = video_dir / scenes[0]["image"] if scenes else None
    thumbnail_path = video_dir / "thumbnail.jpg"
    if thumbnail_source and thumbnail_source.exists():
        shutil.copyfile(thumbnail_source, thumbnail_path)

    providers_used = sorted({scene.get("provider", "") for scene in scenes if scene.get("provider")})
    real_visuals_ready = len(scenes) >= MIN_SCENES and "openai" in providers_used and "placeholder" not in providers_used
    publish_ready = real_visuals_ready
    if "placeholder" in providers_used:
        warnings.append("Placeholder visuals only — not ready for publishing.")

    result = {
        "video_dir": str(video_dir),
        "generated": len(scenes),
        "provider": provider.name,
        "provider_requested": provider_name,
        "providers_used": providers_used,
        "real_visuals_ready": real_visuals_ready,
        "publish_ready": publish_ready,
        "thumbnail": str(thumbnail_path) if thumbnail_path.exists() else None,
        "warnings": warnings,
        "debug": debug,
    }
    _write_scene_manifest(video_dir, provider_name, provider.name, scenes, warnings, result)
    return _write_visual_result(video_dir, result)


def generate_visuals_for_dirs(
    video_dirs: list[Path],
    provider_name: str = "auto",
    force: bool = False,
    allow_placeholder: bool = False,
    debug: bool = False,
) -> dict:
    results = [
        generate_visuals_for_package(
            path,
            provider_name=provider_name,
            force=force,
            allow_placeholder=allow_placeholder,
            debug=debug,
        )
        for path in video_dirs
    ]
    return {
        "attempted": len(video_dirs),
        "generated_count": sum(result.get("generated", 0) for result in results),
        "packages_with_visuals": sum(1 for result in results if result.get("generated", 0) >= MIN_SCENES),
        "warnings": [warning for result in results for warning in result.get("warnings", [])],
        "results": results,
    }


def visuals_available(video_dir: Path) -> bool:
    manifest = load_scene_manifest(video_dir)
    scenes = manifest.get("scenes", [])
    return len([scene for scene in scenes if (video_dir / scene.get("image", "")).exists()]) >= MIN_SCENES


def load_scene_manifest(video_dir: Path) -> dict:
    path = video_dir / "scene-manifest.json"
    if not path.exists():
        return {}
    return _read_json(path)


def load_visual_result(video_dir: Path) -> dict:
    path = video_dir / "visual-result.json"
    if not path.exists():
        return {}
    return _read_json(path)


def normalize_scene_prompts(prompts: dict) -> list[dict]:
    scenes = prompts.get("scenes") if isinstance(prompts, dict) else []
    normalized = []
    for scene in scenes or []:
        prompt = str(scene.get("prompt", "")).strip()
        if prompt:
            normalized.append({"prompt": prompt, "time": scene.get("time", "")})

    if not normalized:
        normalized.append(
            {
                "prompt": "Original vertical 9:16 YouTube Shorts scene, cinematic trend explainer visual, no logos, no copyrighted footage.",
                "time": "0-3s",
            }
        )

    while len(normalized) < MIN_SCENES:
        base = normalized[len(normalized) % len(normalized)]
        normalized.append(
            {
                "prompt": base["prompt"] + " Alternate angle, fresh composition, visual variety.",
                "time": base.get("time", ""),
            }
        )

    return normalized[:MAX_SCENES]


def scene_duration(index: int) -> int:
    return [3, 3, 4, 3, 4, 3, 4, 3][(index - 1) % 8]


def select_provider(provider_name: str) -> ImageProvider:
    provider_name = (provider_name or "auto").lower()
    if provider_name == "openai":
        return OpenAIImageProvider()
    if provider_name == "replicate":
        return ReplicateImageProvider()
    if provider_name in {"placeholder", "fallback"}:
        return PlaceholderImageProvider()

    openai = OpenAIImageProvider()
    if openai.available():
        return openai
    return PlaceholderImageProvider()


def default_visual_provider() -> str:
    return os.getenv("VISUAL_PROVIDER") or os.getenv("IMAGE_PROVIDER", "auto")


def _existing_scene_provider(video_dir: Path, scene_index: int) -> str | None:
    manifest = load_scene_manifest(video_dir)
    for scene in manifest.get("scenes", []):
        if scene.get("scene") == scene_index:
            return scene.get("provider")
    return None


def _write_visual_result(video_dir: Path, result: dict) -> dict:
    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        **result,
    }
    (video_dir / "visual-result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def _write_scene_manifest(
    video_dir: Path,
    provider_requested: str,
    provider_selected: str,
    scenes: list[dict],
    warnings: list[str],
    result: dict,
) -> None:
    thumbnail_path = video_dir / "thumbnail.jpg"
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "provider_requested": provider_requested,
        "provider_selected": provider_selected,
        "scene_count": len(scenes),
        "thumbnail": "thumbnail.jpg" if thumbnail_path.exists() else None,
        "real_visuals_ready": result.get("real_visuals_ready", False),
        "publish_ready": result.get("publish_ready", False),
        "scenes": scenes,
        "warnings": warnings,
    }
    if result.get("openai_error"):
        manifest["openai_error"] = result["openai_error"]
    (video_dir / "scene-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def _redact_prompt_payload(payload: dict | None) -> dict:
    if not payload:
        return {}
    redacted = dict(payload)
    prompt = redacted.get("prompt")
    if isinstance(prompt, str) and len(prompt) > 220:
        redacted["prompt"] = prompt[:220] + "..."
    return redacted


def write_placeholder_png(path: Path, *, prompt: str, seed: int) -> None:
    random.seed(f"{seed}:{prompt}")
    palette = _palette(prompt)
    width = PLACEHOLDER_WIDTH
    height = PLACEHOLDER_HEIGHT
    rows = []
    phase = random.random() * math.pi
    for y in range(height):
        row = bytearray()
        vertical = y / max(height - 1, 1)
        for x in range(width):
            horizontal = x / max(width - 1, 1)
            wave = (math.sin((horizontal * 5.5) + (vertical * 3.2) + phase) + 1) / 2
            band = 1 if (x + y + seed * 37) % 311 < 42 else 0
            r = int(_mix(palette[0][0], palette[1][0], vertical) * 0.72 + palette[2][0] * wave * 0.28)
            g = int(_mix(palette[0][1], palette[1][1], vertical) * 0.72 + palette[2][1] * wave * 0.28)
            b = int(_mix(palette[0][2], palette[1][2], vertical) * 0.72 + palette[2][2] * wave * 0.28)
            if band:
                r = min(255, int(r * 1.16 + 18))
                g = min(255, int(g * 1.16 + 18))
                b = min(255, int(b * 1.16 + 18))
            row.extend((r, g, b))
        rows.append(b"\x00" + bytes(row))
    _write_png(path, width, height, b"".join(rows))


def _write_png(path: Path, width: int, height: int, raw: bytes) -> None:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    png = [
        b"\x89PNG\r\n\x1a\n",
        chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)),
        chunk(b"IDAT", zlib.compress(raw, level=6)),
        chunk(b"IEND", b""),
    ]
    path.write_bytes(b"".join(png))


def _palette(prompt: str) -> tuple[tuple[int, int, int], tuple[int, int, int], tuple[int, int, int]]:
    prompt_l = prompt.lower()
    if "horror" in prompt_l or "creepy" in prompt_l:
        return (18, 16, 24), (92, 20, 28), (214, 63, 45)
    if "animal" in prompt_l:
        return (24, 56, 38), (122, 166, 80), (255, 214, 137)
    if "gaming" in prompt_l:
        return (24, 25, 76), (94, 55, 180), (54, 219, 255)
    if "ai" in prompt_l or "futuristic" in prompt_l:
        return (8, 42, 58), (20, 147, 150), (158, 244, 214)
    if "news" in prompt_l:
        return (18, 35, 55), (50, 91, 140), (255, 212, 92)
    return (20, 28, 42), (50, 96, 130), (239, 107, 99)


def _mix(a: int, b: int, ratio: float) -> float:
    return a + (b - a) * ratio


def _download(url: str, output_path: Path) -> None:
    with urllib.request.urlopen(url, timeout=180) as response:
        output_path.write_bytes(response.read())


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
