from __future__ import annotations

from typing import Any


# v2: form-native output — VLM directly emits form values (no conversion needed)
VLM_REQUIRED_FIELDS = {
    "clear_camera_feed",
    "task_completed_as_instructed",
    "robot_hand_stays_in_frame",
    "all_cameras_in_sync",
    "robot_control_quality",
    "movement_smoothness",
    "task_completion_speed",
    "task_fully_completed",
    "failure_modes",
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

    # PASS/FAIL checks (4 booleans)
    for name in ["clear_camera_feed", "task_completed_as_instructed", "robot_hand_stays_in_frame", "all_cameras_in_sync"]:
        if name in raw and not isinstance(raw.get(name), bool):
            errors.append(f"{name}_not_bool")

    # Quality ratings (4 ints, 1-5)
    for name in ["robot_control_quality", "movement_smoothness", "task_completion_speed", "task_fully_completed"]:
        value = raw.get(name)
        if not isinstance(value, (int, float)) or not 1 <= value <= 5:
            errors.append(f"{name}_out_of_range")

    # Prob/confidence (0.0-1.0)
    for name in ["pass_probability", "confidence"]:
        value = raw.get(name)
        if not isinstance(value, (int, float)) or not 0 <= value <= 1:
            errors.append(f"{name}_out_of_range")

    if not isinstance(raw.get("failure_modes"), list):
        errors.append("failure_modes_not_list")

    if not isinstance(raw.get("reason"), str) or not raw.get("reason", "").strip():
        errors.append("reason_empty")

    if errors:
        return False, None, errors
    return True, raw, []


def score_100_to_slider(value: int | float) -> int:
    """Legacy: convert 0-100 score to 1-5 slider. Keep for backward compat."""
    if value >= 85:
        return 5
    if value >= 70:
        return 4
    if value >= 50:
        return 3
    if value >= 30:
        return 2
    return 1

