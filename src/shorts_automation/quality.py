from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .ai_video import load_ai_video_result
from .stock_videos import video_clips_available
from .visuals import load_visual_result, visuals_available


PUBLISH_THRESHOLD = 72


def score_video_package(video_dir: Path) -> dict:
    video_dir = video_dir.resolve()
    plan = _read_json(video_dir / "video-plan.json")
    scores = plan.get("scores", {})
    script = (video_dir / "script.txt").read_text(encoding="utf-8") if (video_dir / "script.txt").exists() else ""
    has_audio = (video_dir / "voiceover.mp3").exists()
    has_final = (video_dir / "final.mp4").exists()
    has_preview = (video_dir / "preview.mp4").exists()
    has_clips = video_clips_available(video_dir)
    has_visuals = visuals_available(video_dir)
    visual_result = load_visual_result(video_dir)
    ai_video_result = load_ai_video_result(video_dir)
    ai_movie_ready = bool(
        ai_video_result.get("generated_count", 0) >= 4
        and ai_video_result.get("character_consistency_score", 0) >= 75
        and ai_video_result.get("visual_quality_score", 0) >= 75
        and ai_video_result.get("motion_quality_score", 0) >= 70
        and has_final
    )

    hook_score = float(scores.get("hook_score") or _hook_score(script))
    curiosity_score = float(scores.get("curiosity_score", hook_score))
    payoff_score = float(scores.get("payoff_score", hook_score))
    shareability_score = float(scores.get("shareability_score", scores.get("viral_score", 0) or 0))
    completion_probability = float(scores.get("completion_probability", 0) or 0)
    rewatch_probability = float(scores.get("rewatch_probability", 0) or 0)
    visual_score = 92 if has_clips else 72 if visual_result.get("real_visuals_ready") else 48 if has_visuals else 10
    audio_score = 88 if has_audio else 25
    retention_score = min(100, round((completion_probability * 0.45) + (visual_score * 0.25) + (audio_score * 0.2) + (10 if has_preview else 0), 2))
    viral_score = float(scores.get("viral_score") or scores.get("viral_potential_score", 0))
    publish_score = round((retention_score * 0.32) + (viral_score * 0.28) + (hook_score * 0.18) + (visual_score * 0.14) + (audio_score * 0.08), 2)
    publish_ready = publish_score >= PUBLISH_THRESHOLD and has_final and has_audio and ai_movie_ready

    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "video_dir": str(video_dir),
        "retention_score": retention_score,
        "viral_score": viral_score,
        "hook_score": hook_score,
        "curiosity_score": curiosity_score,
        "payoff_score": payoff_score,
        "shareability_score": shareability_score,
        "completion_probability": completion_probability,
        "rewatch_probability": rewatch_probability,
        "visual_score": visual_score,
        "audio_score": audio_score,
        "publish_score": publish_score,
        "publish_ready": publish_ready,
        "ai_movie_ready": ai_movie_ready,
        "character_consistency_score": ai_video_result.get("character_consistency_score", 0),
        "motion_quality_score": ai_video_result.get("motion_quality_score", 0),
        "requirements": {
            "final_mp4": has_final,
            "preview_mp4": has_preview,
            "voiceover_mp3": has_audio,
            "ai_scene_videos": ai_movie_ready,
            "real_video_clips": has_clips,
            "real_ai_visuals": bool(visual_result.get("real_visuals_ready")),
        },
    }
    (video_dir / "quality-score.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def score_video_dirs(video_dirs: list[Path]) -> dict:
    results = [score_video_package(path) for path in video_dirs]
    return {
        "attempted": len(results),
        "publish_ready_count": sum(1 for result in results if result["publish_ready"]),
        "results": results,
    }


def load_quality_score(video_dir: Path) -> dict:
    path = video_dir / "quality-score.json"
    return _read_json(path) if path.exists() else {}


def _hook_score(script: str) -> int:
    lower = script.lower()
    score = 45
    for phrase in ["you won't believe", "hidden detail", "everyone is talking", "exploding", "one reason", "what happened"]:
        if phrase in lower:
            score += 10
    if "hook" in lower:
        score += 10
    return min(score, 100)


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
