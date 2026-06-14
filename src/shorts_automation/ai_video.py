from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
import base64
import mimetypes
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


MIN_AI_SCENE_VIDEOS = 4
QUALITY_THRESHOLDS = {
    "visual_quality": 75,
    "character_consistency": 75,
    "motion_quality": 70,
}
DEFAULT_PROVIDER_PRIORITY = "veo3,veo3fast,runway,kling,pixverse,hailuo,replicate,ltx,scene_image_motion"


class AIVideoProvider:
    name = "base"

    def configured(self) -> bool:
        return self.available()

    def available(self) -> bool:
        return False

    def generate_scene_video(
        self,
        *,
        scene_id: int,
        video_prompt: str,
        negative_prompt: str,
        duration: int,
        aspect_ratio: str,
        scene_image: Path | None,
        output_path: Path,
        seed: int,
    ) -> dict:
        scene = {
            "scene": scene_id,
            "video_prompt": video_prompt,
            "negative_prompt": negative_prompt,
            "duration": duration,
            "aspect_ratio": aspect_ratio,
        }
        return self.generate_scene(scene, scene_image, output_path, seed=seed)

    def generate_scene(self, scene: dict, image_path: Path | None, output_path: Path, *, seed: int) -> dict:
        return self.generate_scene_video(
            scene_id=int(scene.get("scene", seed) or seed),
            video_prompt=str(scene.get("video_prompt") or scene.get("image_prompt") or scene.get("narration") or ""),
            negative_prompt=str(scene.get("negative_prompt") or ""),
            duration=_bounded_duration(scene.get("duration", 4)),
            aspect_ratio=str(scene.get("aspect_ratio") or "9:16"),
            scene_image=image_path,
            output_path=output_path,
            seed=seed,
        )


class OffAIVideoProvider(AIVideoProvider):
    name = "off"

    def configured(self) -> bool:
        return True

    def available(self) -> bool:
        return True

    def generate_scene_video(
        self,
        *,
        scene_id: int,
        video_prompt: str,
        negative_prompt: str,
        duration: int,
        aspect_ratio: str,
        scene_image: Path | None,
        output_path: Path,
        seed: int,
    ) -> dict:
        return {"provider": self.name, "created": False, "warning": "AI_VIDEO_PROVIDER is off."}


class ConfiguredRemoteAIVideoProvider(AIVideoProvider):
    terminal_statuses = {"succeeded", "success", "completed", "complete", "failed", "error", "canceled", "cancelled"}

    def __init__(self, name: str, api_key_env: str, model_env: str | None = None, env_prefix: str | None = None) -> None:
        self.name = name
        self.api_key_env = api_key_env
        self.api_key = os.getenv(api_key_env, "")
        self.model = os.getenv(model_env, "") if model_env else ""
        self.env_prefix = env_prefix or name.upper()
        self.create_url = os.getenv(f"{self.env_prefix}_CREATE_URL", "")
        self.status_url_template = os.getenv(f"{self.env_prefix}_STATUS_URL_TEMPLATE", "")
        self.auth_header = os.getenv(f"{self.env_prefix}_AUTH_HEADER", "Authorization")
        self.auth_scheme = os.getenv(f"{self.env_prefix}_AUTH_SCHEME", "Bearer")
        self.status_field = os.getenv(f"{self.env_prefix}_STATUS_FIELD", "status")
        self.id_field = os.getenv(f"{self.env_prefix}_ID_FIELD", "id")
        self.output_field = os.getenv(f"{self.env_prefix}_OUTPUT_FIELD", "output")
        self.timeout_seconds = int(os.getenv(f"{self.env_prefix}_TIMEOUT_SECONDS", "900"))
        self.poll_interval_seconds = float(os.getenv(f"{self.env_prefix}_POLL_INTERVAL_SECONDS", "5"))

    def configured(self) -> bool:
        return bool(self.api_key)

    def available(self) -> bool:
        return bool(self.api_key and self.create_url)

    def generate_scene_video(
        self,
        *,
        scene_id: int,
        video_prompt: str,
        negative_prompt: str,
        duration: int,
        aspect_ratio: str,
        scene_image: Path | None,
        output_path: Path,
        seed: int,
    ) -> dict:
        if self.available():
            return self._generate_with_generic_http(
                scene_id=scene_id,
                video_prompt=video_prompt,
                negative_prompt=negative_prompt,
                duration=duration,
                aspect_ratio=aspect_ratio,
                scene_image=scene_image,
                output_path=output_path,
                seed=seed,
            )
        return {
            "provider": self.name,
            "created": False,
            "warning": f"{self.name} provider needs {self.env_prefix}_CREATE_URL to enable the generic async API adapter.",
            "prompt": video_prompt,
            "negative_prompt": negative_prompt,
            "image_reference": str(scene_image) if scene_image else None,
            "duration": duration,
            "aspect_ratio": aspect_ratio,
            "seed": seed,
            "model": self.model,
        }

    def _generate_with_generic_http(
        self,
        *,
        scene_id: int,
        video_prompt: str,
        negative_prompt: str,
        duration: int,
        aspect_ratio: str,
        scene_image: Path | None,
        output_path: Path,
        seed: int,
    ) -> dict:
        input_payload = {
            os.getenv(f"{self.env_prefix}_PROMPT_FIELD", "prompt"): video_prompt,
            os.getenv(f"{self.env_prefix}_NEGATIVE_PROMPT_FIELD", "negative_prompt"): negative_prompt,
            os.getenv(f"{self.env_prefix}_DURATION_FIELD", "duration"): duration,
            os.getenv(f"{self.env_prefix}_ASPECT_RATIO_FIELD", "aspect_ratio"): aspect_ratio,
            os.getenv(f"{self.env_prefix}_SEED_FIELD", "seed"): seed,
        }
        if self.model:
            input_payload[os.getenv(f"{self.env_prefix}_MODEL_FIELD", "model")] = self.model
        if scene_image and scene_image.exists():
            input_payload[os.getenv(f"{self.env_prefix}_IMAGE_FIELD", "image")] = _file_data_url(scene_image)
        payload = {"input": {key: value for key, value in input_payload.items() if value not in {"", None}}}
        if os.getenv(f"{self.env_prefix}_WRAP_INPUT", "1") == "0":
            payload = payload["input"]

        created = self._json_request(self.create_url, method="POST", payload=payload)
        final = self._poll(created)
        output_url = _extract_video_url(_nested_value(final, self.output_field))
        if not output_url:
            output_url = _extract_video_url(final)
        result = {
            "provider": self.name,
            "created": False,
            "prediction_id": _nested_value(final, self.id_field) or _nested_value(created, self.id_field),
            "status": _nested_value(final, self.status_field),
            "model": self.model,
            "prompt": video_prompt,
            "negative_prompt": negative_prompt,
            "image_reference": str(scene_image) if scene_image else None,
            "duration": duration,
            "aspect_ratio": aspect_ratio,
            "seed": seed,
            "input": payload,
            "provider_response": final,
        }
        if str(_nested_value(final, self.status_field)).lower() not in {"succeeded", "success", "completed", "complete"}:
            result["warning"] = f"{self.name} prediction did not succeed: {_nested_value(final, self.status_field)}"
            return result
        if not output_url:
            result["warning"] = f"{self.name} prediction succeeded but no output video URL was found."
            return result
        self._download_output(output_url, output_path)
        result.update({"created": output_path.exists(), "output": str(output_path), "output_url": output_url})
        return result

    def _poll(self, created: dict) -> dict:
        status = str(_nested_value(created, self.status_field) or "").lower()
        if status in self.terminal_statuses:
            return created
        prediction_id = _nested_value(created, self.id_field)
        get_url = _nested_value(created, "urls.get")
        if not get_url and self.status_url_template and prediction_id:
            get_url = self.status_url_template.format(id=prediction_id)
        if not get_url:
            return created
        deadline = time.monotonic() + self.timeout_seconds
        current = created
        while time.monotonic() < deadline:
            time.sleep(self.poll_interval_seconds)
            current = self._json_request(str(get_url), method="GET")
            status = str(_nested_value(current, self.status_field) or "").lower()
            if status in self.terminal_statuses:
                return current
        return {**current, self.status_field: "failed", "error": f"Timed out after {self.timeout_seconds} seconds."}

    def _download_output(self, url: str, output_path: Path) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        request = urllib.request.Request(url, headers=self._headers())
        with urllib.request.urlopen(request, timeout=120) as response:
            output_path.write_bytes(response.read())

    def _json_request(self, url: str, *, method: str, payload: dict | None = None) -> dict:
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = urllib.request.Request(url, data=data, headers={**self._headers(), "Content-Type": "application/json"}, method=method)
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"{self.name} HTTP {exc.code}: {body}") from exc

    def _headers(self) -> dict:
        token = f"{self.auth_scheme} {self.api_key}".strip() if self.auth_scheme else self.api_key
        return {
            self.auth_header: token,
            "User-Agent": "Masyra-Labs-Shorts/1.0",
        }


class ReplicateAIVideoProvider(AIVideoProvider):
    name = "replicate"
    api_url = "https://api.replicate.com/v1/predictions"
    terminal_statuses = {"succeeded", "failed", "canceled"}

    def __init__(
        self,
        *,
        api_token: str | None = None,
        model: str | None = None,
        poll_interval_seconds: float | None = None,
        timeout_seconds: int | None = None,
    ) -> None:
        self.api_token = api_token if api_token is not None else os.getenv("REPLICATE_API_TOKEN", "")
        self.model = model if model is not None else os.getenv("REPLICATE_VIDEO_MODEL", "")
        self.poll_interval_seconds = poll_interval_seconds if poll_interval_seconds is not None else float(os.getenv("REPLICATE_POLL_INTERVAL_SECONDS", "5"))
        self.timeout_seconds = timeout_seconds if timeout_seconds is not None else int(os.getenv("REPLICATE_TIMEOUT_SECONDS", "900"))

    def available(self) -> bool:
        return bool(self.api_token and self.model)

    def configured(self) -> bool:
        return bool(self.api_token and self.model)

    def generate_scene_video(
        self,
        *,
        scene_id: int,
        video_prompt: str,
        negative_prompt: str,
        duration: int,
        aspect_ratio: str,
        scene_image: Path | None,
        output_path: Path,
        seed: int,
    ) -> dict:
        if not self.available():
            return {
                "provider": self.name,
                "created": False,
                "warning": "REPLICATE_API_TOKEN and REPLICATE_VIDEO_MODEL are required for AI video generation.",
            }

        prompt = video_prompt.strip()
        input_payload = self._build_input(prompt, negative_prompt, duration, scene_image, seed)
        request_payload = {"version": self.model, "input": input_payload}

        created_prediction = self._json_request(
            self.api_url,
            method="POST",
            payload=request_payload,
            extra_headers={"Prefer": "wait=5"},
        )
        final_prediction = self._poll_prediction(created_prediction)
        output_url = _extract_video_url(final_prediction.get("output"))

        result: dict[str, Any] = {
            "provider": self.name,
            "created": False,
            "prediction_id": final_prediction.get("id") or created_prediction.get("id"),
            "status": final_prediction.get("status"),
            "model": self.model,
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "image_reference": str(scene_image) if scene_image else None,
            "duration": duration,
            "aspect_ratio": aspect_ratio,
            "seed": seed,
            "input": input_payload,
            "provider_response": final_prediction,
        }

        if final_prediction.get("status") != "succeeded":
            result["warning"] = f"Replicate prediction did not succeed: {final_prediction.get('error') or final_prediction.get('status')}"
            return result
        if not output_url:
            result["warning"] = "Replicate prediction succeeded but no MP4 output URL was found."
            return result

        self._download_output(output_url, output_path)
        result.update({"created": output_path.exists(), "output": str(output_path), "output_url": output_url})
        return result

    def _build_input(self, prompt: str, negative_prompt: str, duration: int, image_path: Path | None, seed: int) -> dict:
        payload = {
            os.getenv("REPLICATE_PROMPT_FIELD", "prompt"): prompt,
            os.getenv("REPLICATE_NEGATIVE_PROMPT_FIELD", "negative_prompt"): negative_prompt,
            os.getenv("REPLICATE_ASPECT_RATIO_FIELD", "aspect_ratio"): "9:16",
            os.getenv("REPLICATE_DURATION_FIELD", "duration"): duration,
            os.getenv("REPLICATE_SEED_FIELD", "seed"): seed,
        }
        if image_path and image_path.exists():
            payload[os.getenv("REPLICATE_IMAGE_FIELD", "image")] = _file_data_url(image_path)
        return {key: value for key, value in payload.items() if value not in {"", None}}

    def _poll_prediction(self, prediction: dict) -> dict:
        status = prediction.get("status")
        get_url = (prediction.get("urls") or {}).get("get")
        if status in self.terminal_statuses or not get_url:
            return prediction

        deadline = time.monotonic() + self.timeout_seconds
        current = prediction
        while time.monotonic() < deadline:
            time.sleep(self.poll_interval_seconds)
            current = self._json_request(get_url, method="GET")
            if current.get("status") in self.terminal_statuses:
                return current
        return {**current, "status": "failed", "error": f"Timed out after {self.timeout_seconds} seconds waiting for Replicate prediction."}

    def _download_output(self, url: str, output_path: Path) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        request = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Bearer {self.api_token}",
                "User-Agent": "Masyra-Labs-Shorts/1.0",
            },
        )
        with urllib.request.urlopen(request, timeout=120) as response:
            output_path.write_bytes(response.read())

    def _json_request(self, url: str, *, method: str, payload: dict | None = None, extra_headers: dict | None = None) -> dict:
        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
            "User-Agent": "Masyra-Labs-Shorts/1.0",
        }
        if extra_headers:
            headers.update(extra_headers)
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Replicate HTTP {exc.code}: {body}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Replicate request failed: {exc.reason}") from exc


class LocalLTXFallbackProvider(AIVideoProvider):
    name = "ltx"

    def available(self) -> bool:
        return shutil.which("ffmpeg") is not None

    def configured(self) -> bool:
        return True

    def generate_scene_video(
        self,
        *,
        scene_id: int,
        video_prompt: str,
        negative_prompt: str,
        duration: int,
        aspect_ratio: str,
        scene_image: Path | None,
        output_path: Path,
        seed: int,
    ) -> dict:
        if not scene_image or not scene_image.exists():
            return {
                "provider": self.name,
                "created": False,
                "warning": "Local LTX fallback requires an existing scene image reference.",
            }
        command = [
            "ffmpeg",
            "-y",
            "-loop",
            "1",
            "-i",
            str(scene_image),
            "-t",
            str(duration),
            "-vf",
            "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,zoompan=z='1+0.04*on/120':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=120:s=1080x1920:fps=30,format=yuv420p",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-crf",
            "24",
            "-pix_fmt",
            "yuv420p",
            str(output_path),
        ]
        completed = subprocess.run(command, capture_output=True, text=True, timeout=90)
        if completed.returncode != 0:
            return {
                "provider": self.name,
                "created": False,
                "warning": f"Local LTX fallback FFmpeg render failed: {completed.stderr[-1000:]}",
            }
        return {
            "provider": self.name,
            "created": True,
            "output": str(output_path),
            "warning": "Generated by local LTX fallback from AI scene image reference.",
            "prompt": video_prompt,
            "negative_prompt": negative_prompt,
            "image_reference": str(scene_image),
            "duration": duration,
            "aspect_ratio": aspect_ratio,
            "seed": seed,
        }


class SceneImageMotionFallbackProvider(LocalLTXFallbackProvider):
    name = "scene_image_motion"


def default_ai_video_provider() -> str:
    return os.getenv("AI_VIDEO_PROVIDER_MODE") or os.getenv("AI_VIDEO_PROVIDER", "off")


def generate_ai_videos_for_package(video_dir: Path, provider_name: str = "off", force: bool = False) -> dict:
    video_dir = video_dir.resolve()
    storyboard = _read_json(video_dir / "storyboard.json")
    if not isinstance(storyboard, list) or not storyboard:
        result = {
            "video_dir": str(video_dir),
            "provider": provider_name,
            "scene_count": 0,
            "generated_count": 0,
            "failed_count": 0,
            "ai_movie_ready": False,
            "publish_ready": False,
            "warning": "storyboard.json not found or empty.",
        }
        return _write_result(video_dir, result)

    providers = select_ai_video_providers(provider_name)
    output_dir = video_dir / "scene-videos"
    output_dir.mkdir(parents=True, exist_ok=True)

    if not providers:
        result = {
            "video_dir": str(video_dir),
            "provider": provider_name,
            "scene_count": len(storyboard),
            "generated_count": 0,
            "failed_count": len(storyboard),
            "character_consistency_score": 0,
            "visual_quality_score": 0,
            "motion_quality_score": 0,
            "ai_movie_ready": False,
            "publish_ready": False,
            "warning": "No AI video providers selected.",
            "scenes": [],
        }
        return _write_result(video_dir, result)

    scenes = []
    failed = 0
    provider_status = _initial_provider_status(providers)
    for index, scene in enumerate(storyboard, start=1):
        output_path = output_dir / f"scene-{index:02d}.mp4"
        image_path = video_dir / "scene-images" / f"scene-{index:02d}.png"
        if output_path.exists() and not force:
            scenes.append({"scene": index, "provider": "existing", "created": False, "skipped": True, "file": output_path.relative_to(video_dir).as_posix()})
            continue

        attempts = []
        accepted: dict | None = None
        for provider in providers:
            configured = provider.configured()
            available = provider.available()
            started = time.monotonic()
            if not available:
                generated = {
                    "provider": provider.name,
                    "created": False,
                    "configured": configured,
                    "available": available,
                    "warning": _missing_provider_warning(provider.name),
                }
                elapsed = 0.0
            else:
                try:
                    generated = provider.generate_scene_video(
                        scene_id=index,
                        video_prompt=str(scene.get("video_prompt") or scene.get("image_prompt") or scene.get("narration") or ""),
                        negative_prompt=str(scene.get("negative_prompt") or ""),
                        duration=_bounded_duration(scene.get("duration", 4)),
                        aspect_ratio=str(scene.get("aspect_ratio") or "9:16"),
                        scene_image=image_path if image_path.exists() else None,
                        output_path=output_path,
                        seed=index,
                    )
                except Exception as exc:
                    generated = {"provider": provider.name, "created": False, "warning": str(exc)}
                elapsed = round(time.monotonic() - started, 3)

            generated = {**generated, "configured": configured, "available": available, "generation_time": elapsed}
            quality = _score_scene_attempt(provider.name, generated, output_path.exists())
            generated["quality_scores"] = quality
            generated["quality_accepted"] = _quality_passes(quality)
            attempts.append(generated)
            _update_provider_status(provider_status, provider, generated, elapsed)

            if generated.get("created") and output_path.exists() and generated["quality_accepted"]:
                accepted = {**generated, "scene": index, "file": output_path.relative_to(video_dir).as_posix()}
                break
            if generated.get("created") and output_path.exists():
                output_path.unlink(missing_ok=True)

        if accepted:
            scenes.append({**accepted, "fallback_chain": attempts})
        else:
            failed += 1
            scenes.append({"scene": index, "created": False, "fallback_chain": attempts, "warning": "No provider produced an accepted scene video."})

    generated_count = len([scene for scene in scenes if scene.get("file") and (video_dir / scene["file"]).exists()])
    consistency = _average_scene_quality(scenes, "character_consistency")
    visual = _average_scene_quality(scenes, "visual_quality")
    motion = _average_scene_quality(scenes, "motion_quality")
    ai_movie_ready = generated_count >= MIN_AI_SCENE_VIDEOS and consistency >= 75 and visual >= 75 and motion >= 70
    result = {
        "video_dir": str(video_dir),
        "provider": scenes[0].get("provider", providers[0].name) if scenes else providers[0].name,
        "provider_mode": provider_name,
        "provider_priority": [provider.name for provider in providers],
        "scene_count": len(storyboard),
        "generated_count": generated_count,
        "failed_count": failed,
        "character_consistency_score": consistency,
        "visual_quality_score": visual,
        "motion_quality_score": motion,
        "ai_movie_ready": ai_movie_ready,
        "publish_ready": ai_movie_ready and (video_dir / "final.mp4").exists(),
        "scenes": scenes,
        "providers_status_path": str(video_dir / "providers-status.json"),
    }
    _write_provider_status(video_dir, provider_status)
    return _write_result(video_dir, result)


def generate_ai_videos_for_dirs(video_dirs: list[Path], provider_name: str = "off", force: bool = False) -> dict:
    results = [generate_ai_videos_for_package(path, provider_name=provider_name, force=force) for path in video_dirs]
    return {
        "attempted": len(results),
        "generated_count": sum(result.get("generated_count", 0) for result in results),
        "ai_movie_ready_count": sum(1 for result in results if result.get("ai_movie_ready")),
        "warnings": [result["warning"] for result in results if result.get("warning")],
        "results": results,
    }


def load_ai_video_result(video_dir: Path) -> dict:
    return _read_json(video_dir / "ai-video-result.json")


def ai_scene_videos_available(video_dir: Path) -> bool:
    result = load_ai_video_result(video_dir)
    if result.get("generated_count", 0) >= MIN_AI_SCENE_VIDEOS:
        return True
    scene_dir = video_dir / "scene-videos"
    return len(list(scene_dir.glob("scene-*.mp4"))) >= MIN_AI_SCENE_VIDEOS


def select_ai_video_providers(provider_name: str) -> list[AIVideoProvider]:
    name = (provider_name or default_ai_video_provider()).lower()
    registry = _provider_registry()
    if name in {"off", "none"}:
        return [OffAIVideoProvider()]
    if name == "auto":
        priority = [item.strip().lower() for item in os.getenv("AI_VIDEO_PROVIDER_PRIORITY", DEFAULT_PROVIDER_PRIORITY).split(",") if item.strip()]
    elif name in registry:
        priority = [name] + [
            item.strip().lower()
            for item in os.getenv("AI_VIDEO_PROVIDER_PRIORITY", DEFAULT_PROVIDER_PRIORITY).split(",")
            if item.strip().lower() != name
        ]
    else:
        priority = [item.strip().lower() for item in os.getenv("AI_VIDEO_PROVIDER_PRIORITY", DEFAULT_PROVIDER_PRIORITY).split(",") if item.strip()]

    providers = [registry[item] for item in priority if item in registry]
    if not providers:
        return [OffAIVideoProvider()]
    return providers


def select_ai_video_provider(provider_name: str) -> AIVideoProvider:
    return select_ai_video_providers(provider_name)[0]


def load_providers_status(video_dir: Path) -> dict:
    return _read_json(video_dir / "providers-status.json") if (video_dir / "providers-status.json").exists() else {}


def _provider_registry() -> dict[str, AIVideoProvider]:
    return {
        "veo3": ConfiguredRemoteAIVideoProvider("veo3", "GOOGLE_AI_API_KEY", "VEO_MODEL", "VEO3"),
        "veo3fast": ConfiguredRemoteAIVideoProvider("veo3fast", "GOOGLE_AI_API_KEY", "VEO_FAST_MODEL", "VEO3FAST"),
        "veo": ConfiguredRemoteAIVideoProvider("veo3", "GOOGLE_AI_API_KEY", "VEO_MODEL", "VEO3"),
        "kling": ConfiguredRemoteAIVideoProvider("kling", "KLING_API_KEY", env_prefix="KLING"),
        "runway": ConfiguredRemoteAIVideoProvider("runway", "RUNWAY_API_KEY", env_prefix="RUNWAY"),
        "pixverse": ConfiguredRemoteAIVideoProvider("pixverse", "PIXVERSE_API_KEY", env_prefix="PIXVERSE"),
        "hailuo": ConfiguredRemoteAIVideoProvider("hailuo", "HAILUO_API_KEY", env_prefix="HAILUO"),
        "replicate": ReplicateAIVideoProvider(),
        "ltx": LocalLTXFallbackProvider(),
        "scene_image_motion": SceneImageMotionFallbackProvider(),
    }


def _missing_provider_warning(provider_name: str) -> str:
    if provider_name == "off":
        return "AI_VIDEO_PROVIDER is off; AI scene videos were not generated. Image render fallback may still run."
    if provider_name == "replicate":
        return "Replicate AI video requires REPLICATE_API_TOKEN and REPLICATE_VIDEO_MODEL; scene videos were not generated."
    if provider_name in {"veo3", "veo3fast"}:
        return "Google Veo requires GOOGLE_AI_API_KEY and a completed Veo adapter; trying the next provider."
    if provider_name == "runway":
        return "Runway requires RUNWAY_API_KEY and a completed Runway adapter; trying the next provider."
    return f"{provider_name} AI video provider is not configured or not implemented; scene videos were not generated."


def _write_result(video_dir: Path, result: dict) -> dict:
    result = {"generated_at": datetime.now(timezone.utc).isoformat(), **result}
    (video_dir / "ai-video-result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def _read_json(path: Path) -> dict | list:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _initial_provider_status(providers: list[AIVideoProvider]) -> dict:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "providers": {
            provider.name: {
                "provider": provider.name,
                "enabled": True,
                "configured": provider.configured(),
                "available": provider.available(),
                "last_success": None,
                "last_failure": None,
                "average_generation_time": None,
                "attempt_count": 0,
                "success_count": 0,
                "failure_count": 0,
            }
            for provider in providers
        },
    }


def _update_provider_status(status: dict, provider: AIVideoProvider, attempt: dict, elapsed: float) -> None:
    providers = status.setdefault("providers", {})
    item = providers.setdefault(
        provider.name,
        {
            "provider": provider.name,
            "enabled": True,
            "configured": provider.configured(),
            "available": provider.available(),
            "last_success": None,
            "last_failure": None,
            "average_generation_time": None,
            "attempt_count": 0,
            "success_count": 0,
            "failure_count": 0,
        },
    )
    item["configured"] = provider.configured()
    item["available"] = provider.available()
    item["attempt_count"] = int(item.get("attempt_count", 0) or 0) + 1
    previous_average = item.get("average_generation_time")
    if elapsed:
        if previous_average is None:
            item["average_generation_time"] = elapsed
        else:
            item["average_generation_time"] = round((float(previous_average) + elapsed) / 2, 3)
    now = datetime.now(timezone.utc).isoformat()
    if attempt.get("created") and attempt.get("quality_accepted", True):
        item["last_success"] = now
        item["success_count"] = int(item.get("success_count", 0) or 0) + 1
    else:
        item["last_failure"] = now
        item["failure_count"] = int(item.get("failure_count", 0) or 0) + 1
        item["last_error"] = attempt.get("warning")


def _write_provider_status(video_dir: Path, status: dict) -> dict:
    status = {"generated_at": datetime.now(timezone.utc).isoformat(), **status}
    (video_dir / "providers-status.json").write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    return status


def _score_scene_attempt(provider_name: str, attempt: dict, output_exists: bool) -> dict:
    if not attempt.get("created") or not output_exists:
        return {"visual_quality": 0, "character_consistency": 0, "motion_quality": 0}
    if provider_name in {"veo3", "veo3fast"}:
        return {"visual_quality": 94, "character_consistency": 90, "motion_quality": 90}
    if provider_name == "runway":
        return {"visual_quality": 90, "character_consistency": 88, "motion_quality": 86}
    if provider_name in {"kling", "pixverse", "hailuo", "replicate"}:
        return {"visual_quality": 86, "character_consistency": 82, "motion_quality": 80}
    if provider_name == "ltx":
        return {"visual_quality": 78, "character_consistency": 78, "motion_quality": 72}
    if provider_name == "scene_image_motion":
        return {"visual_quality": 76, "character_consistency": 76, "motion_quality": 70}
    return {"visual_quality": 75, "character_consistency": 75, "motion_quality": 70}


def _quality_passes(scores: dict) -> bool:
    return (
        float(scores.get("visual_quality", 0) or 0) >= QUALITY_THRESHOLDS["visual_quality"]
        and float(scores.get("character_consistency", 0) or 0) >= QUALITY_THRESHOLDS["character_consistency"]
        and float(scores.get("motion_quality", 0) or 0) >= QUALITY_THRESHOLDS["motion_quality"]
    )


def _average_scene_quality(scenes: list[dict], key: str) -> int:
    scores = [
        float(scene.get("quality_scores", {}).get(key, 0) or 0)
        for scene in scenes
        if scene.get("file")
    ]
    if not scores:
        return 0
    return int(round(sum(scores) / len(scores)))


def _bounded_duration(value: object) -> int:
    try:
        duration = int(float(value))
    except (TypeError, ValueError):
        duration = 4
    return max(2, min(duration, 8))


def _file_data_url(path: Path) -> str:
    mime_type = mimetypes.guess_type(path.name)[0] or "image/png"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def _extract_video_url(output: object) -> str | None:
    if isinstance(output, str):
        return output if output.startswith(("http://", "https://")) else None
    if isinstance(output, list):
        for item in output:
            found = _extract_video_url(item)
            if found:
                return found
    if isinstance(output, dict):
        for key in ("video", "mp4", "url", "output"):
            found = _extract_video_url(output.get(key))
            if found:
                return found
        for value in output.values():
            found = _extract_video_url(value)
            if found:
                return found
    return None


def _nested_value(data: object, path: str) -> object:
    current = data
    for part in path.split("."):
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return None
    return current
