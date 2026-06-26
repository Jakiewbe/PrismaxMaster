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
    "daily_workflow": {
        "enabled": True,
        "control_first": True,
        "min_control_operations_before_vla": 1,
        "min_labels_per_day": 2,
        "max_labels_per_day": 4,
        "daily_counts_path": "data/logs/vla_daily_counts.json",
        "control_state_file": "../prismax_state.json",
        "block_if_control_state_missing": False,
        "api_keys_location": "python_env_only",
    },
    "playback": {
        "enabled": True,
        "speed_multiplier": 10.0,
        "sample_every_n_frames": 2,
        "simulate_delay": True,
        "segment_gap_seconds": 1.5,
    },
    "scorer": {"version": "v0.5.0"},
    "vlm": {
        "enabled": False,
        "export_requests": True,
        "request_dir": "data/logs/vlm_requests",
        "prompt_template": "vlm_prompts/prismax_vla_v1.txt",
        "prompt_version": "prismax_vla_v1",
        "provider": "manual",
        "model": None,
        "timeout_seconds": 90,
        "max_retries": 2,
        "temperature": 0.0,
        "max_images": 20,
        "allow_text_only_primary": False,
        "response_dir": "data/logs/vlm_responses",
        "provider_profiles": {
            "openai_compatible": {
                "base_url": "https://api.openai.com/v1/chat/completions",
                "api_key_env": "OPENAI_API_KEY",
                "model": "gpt-4o-mini",
                "response_format_json": True,
            },
            "deepseek_text": {
                "base_url": "https://api.deepseek.com/chat/completions",
                "api_key_env": "DEEPSEEK_API_KEY",
                "model": "deepseek-chat",
                "text_only": True,
                "response_format_json": True,
            },
            "xiaomi_compatible": {
                "base_url": "",
                "api_key_env": "XIAOMI_API_KEY",
                "model": "",
                "response_format_json": True,
            },
        },
    },
    "browser": {
        "urls": {
            "dashboard": "https://app.prismax.ai/",
            "review_list": "https://app.prismax.ai/data/review",
            "review_detail_pattern": "https://app.prismax.ai/data/review/{task_id}?upload={upload_id}",
        },
        "selectors": {
            "begin_validating_button": "button:has-text('Begin Validating')",
            "review_earn_button": "button:has-text('Review & Earn')",
            "submit_button": ".DataQAReview_submitBtn__I7VB7",
            "scenario_trigger": ".DataQAReview_scenarioTrigger__qCwVC",
            "breadcrumb": ".DataQAReview_breadcrumbLink__uMtJZ",
            "playback_speed": ".DataQAReview_ctrlSpeed__G1Whv",
            "validation_rules_link": ".DataQAReview_valLink__Od5GV",
            "videos": "video",
            "form_grid_table": "table.DataQAReview_gridTable__AbOV0",
            "form_row": "table.DataQAReview_gridTable__AbOV0 tbody tr",
            "form_cell": "td.DataQAReview_gridTdCenter__u0I-h",
            "form_dot": ".DataQAReview_dot__u0Ot0",
            "form_dot_selected": ".DataQAReview_dot__u0Ot0.DataQAReview_dotSelected__",
            "form_row_label": ".DataQAReview_rowLabelText__v2yHF",
            "scoring_panel": ".DataQAReview_panel__0xNzL",
            "pass_fail_label": ".DataQAReview_rLabel__FE-lY",
            "score_section": ".DataQAReview_scoreSection__iWLub",
            "gate_score_value": ".DataQAReview_statVal__sHAXi",
        },
        "text_patterns": {"episode_id": r"Episode #(\d+)", "progress": r"(\d+) of (\d+)"},
        "click_method": "react_dot",
        "click_events": ["mousedown", "mouseup", "click"],
    },
    "form": {
        "pass_fail_items": {
            "clear_camera_feed": {
                "label": "Clear camera feed",
                "fail_modes": ["black_frame", "brightness", "blur", "camera_feed", "required_view_missing", "video_error"],
            },
            "task_completed_as_instructed": {
                "label": "Task completed as instructed",
                "fail_modes": ["task_not_completed", "task_mismatch", "failure_detected", "low_pass_probability"],
            },
            "robot_hand_stays_in_frame": {
                "label": "Robot hand stays in frame",
                "fail_modes": ["hand_out_of_frame", "robot_hand", "optional_view_missing"],
            },
            "all_cameras_in_sync": {
                "label": "All cameras in sync",
                "fail_modes": ["camera_sync", "sync", "freeze_ratio"],
            },
        },
        "quality_sliders": {
            "quality": {"label": "Robot control quality", "order": 0},
            "smoothness": {"label": "Movement smoothness", "order": 1},
            "speed": {"label": "Task completion speed", "order": 2},
            "completion": {"label": "Task fully completed", "order": 3},
        },
        "slider_labels": {1: "Poor", 2: "Weak", 3: "OK", 4: "Good", 5: "Exc"},
    },
    "views": {
        "main": {"required": True, "role": "global", "hard_fail_if_missing": True},
        "left_wrist": {"required": False, "role": "manipulator"},
        "right_wrist": {"required": False, "role": "manipulator"},
    },
    "rules": {
        "black_frame": {"hard_fail": 0.50, "suspicious": 0.12},
        "freeze_ratio": {"hard_fail": 0.95, "suspicious": 0.45},
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
        "hard_fail": {"speed": 1, "smoothness": 1, "quality": 1, "completion": 1},
        "uncertain": {"speed": 3, "smoothness": 3, "quality": 3, "completion": 3},
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


