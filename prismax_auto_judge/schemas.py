from __future__ import annotations

from typing import Any


VLM_REQUIRED_FIELDS = {
    "task_matches_prompt",
    "task_success_score",
    "completion_score",
    "final_state_score",
    "trajectory_clarity_score",
    "smoothness_score",
    "speed_score",
    "diversity_score",
    "no_damage_score",
    "failure_detected",
    "failure_modes",
    "destructive_action",
    "long_stuck_or_struggle",
    "pass_probability",
    "confidence",
    "reason",
}


def validate_vlm_output(raw: Any) -> tuple[bool, dict[str, Any] | None, list[str]]:
    errors: list[str] = []
    if not isinstance(raw, dict):
        return False, None, ["vlm_output_not_object"]

    missing = sorted(VLM_REQUIRED_FIELDS - set(raw))
    if missing:
        errors.append("missing_fields:" + ",".join(missing))

    for name in [
        "task_success_score",
        "completion_score",
        "final_state_score",
        "trajectory_clarity_score",
        "smoothness_score",
        "speed_score",
        "diversity_score",
        "no_damage_score",
    ]:
        value = raw.get(name)
        if not isinstance(value, (int, float)) or not 0 <= value <= 100:
            errors.append(f"{name}_out_of_range")

    for name in ["pass_probability", "confidence"]:
        value = raw.get(name)
        if not isinstance(value, (int, float)) or not 0 <= value <= 1:
            errors.append(f"{name}_out_of_range")

    for name in ["task_matches_prompt", "failure_detected", "destructive_action", "long_stuck_or_struggle"]:
        if not isinstance(raw.get(name), bool):
            errors.append(f"{name}_not_bool")

    if not isinstance(raw.get("failure_modes"), list):
        errors.append("failure_modes_not_list")

    if not isinstance(raw.get("reason"), str) or not raw.get("reason", "").strip():
        errors.append("reason_empty")

    if errors:
        return False, None, errors
    return True, raw, []


def score_100_to_slider(value: int | float) -> int:
    if value >= 85:
        return 5
    if value >= 70:
        return 4
    if value >= 50:
        return 3
    if value >= 30:
        return 2
    return 1

