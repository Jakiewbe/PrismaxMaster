from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any


DEFAULT_CONFIG: dict[str, Any] = {
    "runtime": {
        "mode": "dry_run",
        "auto_submit": False,
        "skip_uncertain": True,
        "save_log": True,
        "log_path": "data/logs/scoring_log.jsonl",
        "processed_registry_path": "data/logs/processed_episodes.json",
        "local_video_dir": "data/videos",
    },
    "scorer": {"version": "v0.1.0"},
    "views": {
        "main": {"required": True, "role": "global", "hard_fail_if_missing": True},
        "left_wrist": {"required": False, "role": "manipulator"},
        "right_wrist": {"required": False, "role": "manipulator"},
    },
    "rules": {
        "black_frame": {"hard_fail": 0.50, "suspicious": 0.12},
        "freeze_ratio": {"hard_fail": 0.80, "suspicious": 0.30},
        "blur_score": {"hard_fail": 10, "suspicious": 35},
        "brightness": {
            "hard_fail_min": 5,
            "suspicious_min": 25,
            "hard_fail_max": 250,
            "suspicious_max": 235,
        },
        "motion_energy": {"hard_fail": 0.3, "suspicious": 1.5},
        "start_end_diff": {"hard_fail": None, "suspicious": 5},
        "idle_ratio": {"hard_fail": None, "suspicious": 0.55},
    },
    "decision_thresholds": {
        "auto_pass_min_probability": 0.86,
        "auto_fail_max_probability": 0.25,
        "min_confidence_submit": 0.78,
    },
    "safety": {
        "require_episode_id_match_before_submit": True,
        "require_manual_enable_auto": True,
        "allow_auto_fail_submit": False,
        "max_auto_submit_per_run": 10,
        "stop_on_first_submit_error": True,
        "submit_cooldown_seconds": 2,
    },
    "frame_sampling": {
        "percent_points": [0, 10, 25, 50, 75, 90, 100],
        "include_motion_peak": True,
        "include_long_idle_edges": True,
    },
    "default_scores": {
        "hard_fail": {"speed": 1, "smoothness": 1, "quality": 1, "diversity": 3, "completion": 1},
        "uncertain": {"speed": 3, "smoothness": 3, "quality": 3, "diversity": 3, "completion": 3},
    },
}


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_config(config_path: str | Path | None = None) -> tuple[dict[str, Any], str]:
    config = copy.deepcopy(DEFAULT_CONFIG)
    path = Path(config_path) if config_path else Path(__file__).with_name("config.yaml")
    raw_text = ""
    if path.exists():
        raw_text = path.read_text(encoding="utf-8")
        try:
            import yaml  # type: ignore

            loaded = yaml.safe_load(raw_text) or {}
            if not isinstance(loaded, dict):
                raise ValueError("config root must be a mapping")
            config = deep_merge(config, loaded)
        except ModuleNotFoundError:
            # Keep defaults. requirements.txt declares PyYAML for real config parsing.
            pass
    digest_src = json.dumps(config, ensure_ascii=False, sort_keys=True)
    config_hash = hashlib.sha256(digest_src.encode("utf-8")).hexdigest()[:12]
    return config, config_hash


def resolve_data_path(path: str | Path) -> Path:
    path_obj = Path(path)
    if path_obj.is_absolute():
        return path_obj
    return Path(__file__).resolve().parent / path_obj

