from __future__ import annotations

import argparse
import time
from typing import Any

from config_loader import load_config, resolve_data_path
from control_adapter import iter_local_episodes
from judge_logger import JsonlLogger
from processed_registry import ProcessedRegistry
from scorer import PrismaXScorer


VALID_MODES = {"dry_run", "assist_preview", "assist_fill", "auto"}


def build_log_record(
    episode: dict[str, Any],
    result: dict[str, Any],
    mode: str,
    config_hash: str,
    scorer_version: str,
    control_record: dict[str, Any],
) -> dict[str, Any]:
    return {
        "mode": mode,
        "scorer_version": scorer_version,
        "config_hash": config_hash,
        "episode": episode,
        "features": result.get("features", {}),
        "rules": result.get("rules", {}),
        "frames": result.get("frames", {}),
        "vlm": result.get("vlm", {}),
        "decision": {
            "decision": result.get("decision"),
            "should_submit": result.get("should_submit"),
            "confidence": result.get("confidence"),
            "reason": result.get("reason"),
            "scores": result.get("scores"),
            "pass_probability": result.get("pass_probability"),
        },
        "form_plan": result.get("form_plan", {}),
        "control": control_record,
        "error": result.get("error"),
    }


def apply_local_mode(result: dict[str, Any], mode: str, config: dict[str, Any], auto_submit_count: int) -> tuple[dict[str, Any], int]:
    control_record = {
        "submitted": False,
        "submit_status": mode,
        "page_episode_id_before_submit": None,
        "page_episode_id_after_submit": None,
    }

    if mode in {"dry_run", "assist_preview"}:
        control_record["submit_status"] = mode
        return control_record, auto_submit_count

    if mode == "assist_fill":
        control_record["submit_status"] = "live_control_not_implemented"
        return control_record, auto_submit_count

    if mode == "auto":
        safety = config.get("safety", {})
        if result.get("decision") == "FAIL" and not safety.get("allow_auto_fail_submit", False):
            control_record["submit_status"] = "auto_fail_submit_disabled"
            return control_record, auto_submit_count
        if not result.get("should_submit"):
            control_record["submit_status"] = "not_submittable"
            return control_record, auto_submit_count
        if auto_submit_count >= int(safety.get("max_auto_submit_per_run", 10)):
            control_record["submit_status"] = "max_auto_submit_per_run_reached"
            return control_record, auto_submit_count
        control_record["submit_status"] = "live_control_not_implemented"
        return control_record, auto_submit_count

    control_record["submit_status"] = "unknown_mode"
    return control_record, auto_submit_count


def run_local_batch(config: dict[str, Any], config_hash: str, video_dir: str | None = None) -> int:
    runtime = config["runtime"]
    mode = runtime.get("mode", "dry_run")
    if mode not in VALID_MODES:
        raise ValueError(f"invalid runtime.mode:{mode}")

    log_path = resolve_data_path(runtime["log_path"])
    registry_path = resolve_data_path(runtime["processed_registry_path"])
    local_video_dir = video_dir or runtime.get("local_video_dir", "data/videos")
    video_root = resolve_data_path(local_video_dir)

    logger = JsonlLogger(log_path)
    registry = ProcessedRegistry(registry_path)
    scorer = PrismaXScorer(config, config_hash)

    processed_count = 0
    auto_submit_count = 0
    for episode in iter_local_episodes(video_root):
        episode_id = str(episode["episode_id"])
        if registry.is_submitted(episode_id):
            continue
        result = scorer.score_episode(episode)
        control_record, auto_submit_count = apply_local_mode(result, mode, config, auto_submit_count)
        logger.write(build_log_record(episode, result, mode, config_hash, scorer.version, control_record))
        registry.mark(episode_id, str(result.get("decision")), bool(control_record.get("submitted")))
        processed_count += 1
        print(f"{episode_id}: {result['decision']} submit={control_record['submitted']} reason={result['reason']}")
        if mode == "auto" and control_record.get("submitted"):
            auto_submit_count += 1
            time.sleep(float(config.get("safety", {}).get("submit_cooldown_seconds", 2)))

    if processed_count == 0:
        print(f"No local videos found in {video_root}")
    return processed_count


def main() -> int:
    parser = argparse.ArgumentParser(description="PrismaX VLA auto judge v0")
    parser.add_argument("--config", default=None, help="Path to config.yaml")
    parser.add_argument("--video-dir", default=None, help="Local video folder for dry-run batch")
    args = parser.parse_args()

    config, config_hash = load_config(args.config)
    run_local_batch(config, config_hash, args.video_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
