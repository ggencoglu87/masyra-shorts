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
    tts_result = _read_json(video_dir / "tts-result.json")
    has_audio = (video_dir / "voiceover.mp3").exists()
    has_mixed_audio = bool(has_audio and (tts_result.get("mixed_voiceover_ready", has_audio)) and tts_result.get("audio_matches_current_text", has_audio))
    has_captions = (video_dir / "captions.json").exists() and bool(_read_json(video_dir / "captions.json"))
    captions_clean = _captions_have_clean_words(video_dir)
    estimated_episode_duration = float(tts_result.get("estimated_duration") or tts_result.get("estimated_episode_duration") or _storyboard_duration(video_dir) or 0)
    actual_audio_duration = _actual_audio_duration(video_dir, tts_result)
    dialogue_percentage = float(tts_result.get("dialogue_percentage") or _dialogue_percentage(video_dir) or 0)
    dialogue_line_count = int(tts_result.get("dialogue_line_count") or _dialogue_line_count(video_dir) or 0)
    speaker_count = int(tts_result.get("speaker_count") or len(tts_result.get("voices_used", [])) or _speaker_count(video_dir) or 0)
    duration_ready = actual_audio_duration is not None and 25 <= actual_audio_duration <= 35
    dialogue_ready = dialogue_percentage >= 30
    line_count_ready = dialogue_line_count >= 20
    has_final = (video_dir / "final.mp4").exists()
    has_preview = (video_dir / "preview.mp4").exists()
    has_clips = video_clips_available(video_dir)
    has_visuals = visuals_available(video_dir)
    visual_result = load_visual_result(video_dir)
    ai_video_result = load_ai_video_result(video_dir)
    real_ai_scene_count = int(ai_video_result.get("real_ai_scene_count", 0) or 0)
    image_motion_scene_count = int(ai_video_result.get("image_motion_scene_count", 0) or 0)
    image_only_scene_count = int(ai_video_result.get("image_only_scene_count", 0) or 0)
    ai_movie_ready = bool(
        real_ai_scene_count >= 4
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
    audio_score = 92 if has_mixed_audio else 88 if has_audio else 25
    retention_score = min(100, round((completion_probability * 0.45) + (visual_score * 0.25) + (audio_score * 0.2) + (10 if has_preview else 0), 2))
    viral_score = float(scores.get("viral_score") or scores.get("viral_potential_score", 0))
    publish_score = round((retention_score * 0.32) + (viral_score * 0.28) + (hook_score * 0.18) + (visual_score * 0.14) + (audio_score * 0.08), 2)
    publish_ready = (
        publish_score >= PUBLISH_THRESHOLD
        and has_final
        and has_mixed_audio
        and has_captions
        and captions_clean
        and ai_movie_ready
        and duration_ready
        and dialogue_ready
        and line_count_ready
    )

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
        "estimated_episode_duration": estimated_episode_duration,
        "estimated_duration": estimated_episode_duration,
        "actual_audio_duration": actual_audio_duration,
        "dialogue_percentage": dialogue_percentage,
        "dialogue_line_count": dialogue_line_count,
        "line_count": dialogue_line_count,
        "speaker_count": speaker_count,
        "voice_separation_mode": tts_result.get("voice_separation_mode", "single"),
        "publish_score": publish_score,
        "publish_ready": publish_ready,
        "ai_movie_ready": ai_movie_ready,
        "real_ai_scene_count": real_ai_scene_count,
        "image_motion_scene_count": image_motion_scene_count,
        "image_only_scene_count": image_only_scene_count,
        "character_consistency_score": ai_video_result.get("character_consistency_score", 0),
        "motion_quality_score": ai_video_result.get("motion_quality_score", 0),
        "requirements": {
            "final_mp4": has_final,
            "preview_mp4": has_preview,
            "voiceover_mp3": has_audio,
            "mixed_voiceover_mp3": has_mixed_audio,
            "captions": has_captions,
            "caption_validation": captions_clean,
            "actual_audio_duration_25_to_35": duration_ready,
            "dialogue_percentage_30_plus": dialogue_ready,
            "line_count_20_plus": line_count_ready,
            "speaker_count": speaker_count,
            "ai_scene_videos": ai_movie_ready,
            "real_ai_scene_count": real_ai_scene_count,
            "image_motion_scene_count": image_motion_scene_count,
            "image_only_scene_count": image_only_scene_count,
            "real_video_clips": has_clips,
            "real_ai_visuals": bool(visual_result.get("real_visuals_ready")),
        },
    }
    for filename in ("quality-score.json", "quality-result.json"):
        (video_dir / filename).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def score_video_dirs(video_dirs: list[Path]) -> dict:
    results = [score_video_package(path) for path in video_dirs]
    return {
        "attempted": len(results),
        "publish_ready_count": sum(1 for result in results if result["publish_ready"]),
        "results": results,
    }


def load_quality_score(video_dir: Path) -> dict:
    for filename in ("quality-result.json", "quality-score.json"):
        path = video_dir / filename
        if path.exists():
            return _read_json(path)
    return {}


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


def _captions_have_clean_words(video_dir: Path) -> bool:
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


def _storyboard_duration(video_dir: Path) -> float:
    storyboard = _read_json(video_dir / "storyboard.json")
    if not isinstance(storyboard, list):
        return 0.0
    return float(sum(float(scene.get("duration", 0) or 0) for scene in storyboard if isinstance(scene, dict)))


def _dialogue_percentage(video_dir: Path) -> float:
    storyboard = _read_json(video_dir / "storyboard.json")
    if not isinstance(storyboard, list):
        return 0.0
    lines = []
    for scene in storyboard:
        if isinstance(scene, dict):
            lines.extend(line for line in scene.get("dialogue", []) if isinstance(line, dict))
    character_lines = [line for line in lines if line.get("speaker_id") != "narrator"]
    return round((len(character_lines) / max(len(lines), 1)) * 100, 2)


def _speaker_count(video_dir: Path) -> int:
    storyboard = _read_json(video_dir / "storyboard.json")
    if not isinstance(storyboard, list):
        return 0
    speakers = set()
    for scene in storyboard:
        if isinstance(scene, dict):
            speakers.update(line.get("speaker_id") for line in scene.get("dialogue", []) if isinstance(line, dict) and line.get("speaker_id"))
    return len(speakers)


def _dialogue_line_count(video_dir: Path) -> int:
    storyboard = _read_json(video_dir / "storyboard.json")
    if not isinstance(storyboard, list):
        return 0
    count = 0
    for scene in storyboard:
        if isinstance(scene, dict):
            count += len([line for line in scene.get("dialogue", []) if isinstance(line, dict) and line.get("line")])
    return count


def _actual_audio_duration(video_dir: Path, tts_result: dict) -> float | None:
    if tts_result.get("actual_audio_duration") is not None:
        try:
            return float(tts_result["actual_audio_duration"])
        except (TypeError, ValueError):
            return None
    return None
