from __future__ import annotations

from typing import Any

from frame_sampler import sample_episode_frames
from schemas import score_100_to_slider, validate_vlm_output
from video_features import analyze_episode_videos
from vlm_client import VLMClient


class PrismaXScorer:
    def __init__(self, config: dict[str, Any], config_hash: str):
        self.config = config
        self.config_hash = config_hash
        self.version = config.get("scorer", {}).get("version", "v0.2.0")
        self.vlm = VLMClient(config)

    def score_episode(self, episode: dict[str, Any]) -> dict[str, Any]:
        episode_id = str(episode.get("episode_id", "unknown"))
        try:
            features, video_errors = analyze_episode_videos(episode, self.config)
            hard_fail_reasons, suspicious_reasons, triggered_thresholds = self._evaluate_rules(features, video_errors)

            if any(reason.startswith("video_error:") for reason in video_errors):
                return self._result(
                    episode_id,
                    "ERROR",
                    False,
                    0.0,
                    "high",
                    "Video read or dependency error.",
                    features,
                    hard_fail_reasons,
                    suspicious_reasons,
                    triggered_thresholds,
                    error={"video_errors": video_errors},
                )

            frames = sample_episode_frames(episode, features, self.config)

            if hard_fail_reasons:
                return self._result(
                    episode_id,
                    "FAIL",
                    True,
                    0.95,
                    "low",
                    "Deterministic hard fail.",
                    features,
                    hard_fail_reasons,
                    suspicious_reasons,
                    triggered_thresholds,
                    frames=frames,
                    scores=self.config["default_scores"]["hard_fail"],
                )

            if suspicious_reasons:
                return self._result(
                    episode_id,
                    "UNCERTAIN",
                    False,
                    0.45,
                    "medium",
                    "Suspicious visual signals require semantic review.",
                    features,
                    hard_fail_reasons,
                    suspicious_reasons,
                    triggered_thresholds,
                    frames=frames,
                )

            vlm_raw = self.vlm.judge_episode(
                task_prompt=str(episode.get("task_prompt", "")),
                frame_paths=frames,
                video_paths=episode.get("video_paths") or {},
            )
            if vlm_raw is None:
                return self._result(
                    episode_id,
                    "UNCERTAIN",
                    False,
                    0.50,
                    "medium",
                    "No VLM configured; normal videos cannot be auto-passed.",
                    features,
                    hard_fail_reasons,
                    suspicious_reasons,
                    triggered_thresholds,
                    frames=frames,
                    vlm={"used": False, "model": None, "prompt_version": None, "raw_output": None},
                )

            valid, vlm, validation_errors = validate_vlm_output(vlm_raw)
            if not valid or vlm is None:
                return self._result(
                    episode_id,
                    "UNCERTAIN",
                    False,
                    0.0,
                    "high",
                    "Invalid VLM output.",
                    features,
                    hard_fail_reasons,
                    suspicious_reasons,
                    triggered_thresholds,
                    frames=frames,
                    vlm={"used": True, "model": self.vlm.model_name, "prompt_version": self.vlm.prompt_version, "raw_output": vlm_raw},
                    error={"vlm_validation_errors": validation_errors},
                )

            return self._decide_from_vlm(episode_id, features, hard_fail_reasons, suspicious_reasons, triggered_thresholds, frames, vlm)
        except Exception as exc:
            return self._result(
                episode_id,
                "ERROR",
                False,
                0.0,
                "high",
                f"Scorer error: {exc}",
                {},
                [],
                [],
                [],
                error={"type": type(exc).__name__, "message": str(exc)},
            )

    def _evaluate_rules(
        self,
        features: dict[str, Any],
        video_errors: list[str],
    ) -> tuple[list[str], list[str], list[dict[str, Any]]]:
        hard: list[str] = []
        suspicious: list[str] = []
        triggered: list[dict[str, Any]] = []
        rules = self.config.get("rules", {})

        for err in video_errors:
            if err.startswith("required_view_missing:"):
                hard.append(err)

        for view_name, view_features in features.items():
            if view_name.startswith("_"):
                continue
            if not isinstance(view_features, dict):
                continue
            if not view_features.get("present", False):
                if view_features.get("required"):
                    hard.append(f"required_view_missing:{view_name}")
                continue
            if "error" in view_features:
                continue
            prefix = f"{view_name}:"
            self._check_min_max(
                view_features.get("black_frame_ratio"),
                rules["black_frame"],
                prefix + "black_frame_ratio",
                hard,
                suspicious,
                triggered,
                high_is_bad=True,
            )
            self._check_min_max(
                view_features.get("freeze_ratio"),
                rules["freeze_ratio"],
                prefix + "freeze_ratio",
                hard,
                suspicious,
                triggered,
                high_is_bad=True,
            )
            self._check_min_max(
                view_features.get("blur_score"),
                rules["blur_score"],
                prefix + "blur_score",
                hard,
                suspicious,
                triggered,
                high_is_bad=False,
            )
            self._check_brightness(view_features.get("brightness_mean"), rules["brightness"], prefix, hard, suspicious, triggered)
            self._check_min_max(
                view_features.get("motion_energy"),
                rules["motion_energy"],
                prefix + "motion_energy",
                hard,
                suspicious,
                triggered,
                high_is_bad=False,
            )
            self._check_min_max(
                view_features.get("start_end_diff"),
                rules["start_end_diff"],
                prefix + "start_end_diff",
                hard,
                suspicious,
                triggered,
                high_is_bad=False,
            )
            self._check_min_max(
                view_features.get("idle_ratio"),
                rules["idle_ratio"],
                prefix + "idle_ratio",
                hard,
                suspicious,
                triggered,
                high_is_bad=True,
            )
            if view_features.get("frame_count", 1) <= 0 or view_features.get("duration_seconds", 1) <= 0:
                hard.append(prefix + "zero_length_video")
                triggered.append({"rule": prefix + "zero_length_video", "value": view_features.get("duration_seconds"), "threshold": 0})

        return sorted(set(hard)), sorted(set(suspicious)), triggered

    @staticmethod
    def _check_min_max(
        value: Any,
        rule_cfg: dict[str, Any],
        name: str,
        hard: list[str],
        suspicious: list[str],
        triggered: list[dict[str, Any]],
        high_is_bad: bool,
    ) -> None:
        if not isinstance(value, (int, float)):
            return
        hard_threshold = rule_cfg.get("hard_fail")
        suspicious_threshold = rule_cfg.get("suspicious")
        if hard_threshold is not None:
            bad = value >= hard_threshold if high_is_bad else value <= hard_threshold
            if bad:
                hard.append(name)
                triggered.append({"rule": name, "level": "hard_fail", "value": value, "threshold": hard_threshold})
                return
        if suspicious_threshold is not None:
            bad = value >= suspicious_threshold if high_is_bad else value <= suspicious_threshold
            if bad:
                suspicious.append(name)
                triggered.append({"rule": name, "level": "suspicious", "value": value, "threshold": suspicious_threshold})

    @staticmethod
    def _check_brightness(
        value: Any,
        rule_cfg: dict[str, Any],
        prefix: str,
        hard: list[str],
        suspicious: list[str],
        triggered: list[dict[str, Any]],
    ) -> None:
        if not isinstance(value, (int, float)):
            return
        checks = [
            ("brightness_low", "hard_fail", value <= rule_cfg["hard_fail_min"], rule_cfg["hard_fail_min"]),
            ("brightness_high", "hard_fail", value >= rule_cfg["hard_fail_max"], rule_cfg["hard_fail_max"]),
            ("brightness_low", "suspicious", value <= rule_cfg["suspicious_min"], rule_cfg["suspicious_min"]),
            ("brightness_high", "suspicious", value >= rule_cfg["suspicious_max"], rule_cfg["suspicious_max"]),
        ]
        for name, level, bad, threshold in checks:
            if bad:
                target = hard if level == "hard_fail" else suspicious
                target.append(prefix + name)
                triggered.append({"rule": prefix + name, "level": level, "value": value, "threshold": threshold})
                return

    def _decide_from_vlm(
        self,
        episode_id: str,
        features: dict[str, Any],
        hard_fail_reasons: list[str],
        suspicious_reasons: list[str],
        triggered_thresholds: list[dict[str, Any]],
        frames: dict[str, list[str]],
        vlm: dict[str, Any],
    ) -> dict[str, Any]:
        thresholds = self.config["decision_thresholds"]
        pass_probability = float(vlm["pass_probability"])
        confidence = float(vlm["confidence"])
        scores = {
            "speed": score_100_to_slider(vlm["speed_score"]),
            "smoothness": score_100_to_slider(vlm["smoothness_score"]),
            "quality": score_100_to_slider(vlm["final_state_score"]),
            "completion": score_100_to_slider(vlm["completion_score"]),
        }
        vlm_log = {"used": True, "model": self.vlm.model_name, "prompt_version": self.vlm.prompt_version, "raw_output": vlm}

        if (
            pass_probability >= thresholds["auto_pass_min_probability"]
            and confidence >= thresholds["min_confidence_submit"]
            and vlm["task_matches_prompt"] is True
            and vlm["failure_detected"] is False
            and vlm["destructive_action"] is False
        ):
            return self._result(
                episode_id, "PASS", True, confidence, "low", vlm["reason"], features,
                hard_fail_reasons, suspicious_reasons, triggered_thresholds, frames=frames,
                scores=scores, pass_probability=pass_probability, failure_modes=vlm["failure_modes"], vlm=vlm_log,
            )

        if (
            (pass_probability <= thresholds["auto_fail_max_probability"] and confidence >= thresholds["min_confidence_submit"])
            or vlm["task_matches_prompt"] is False
            or vlm["destructive_action"] is True
        ):
            return self._result(
                episode_id, "FAIL", True, confidence, "low", vlm["reason"], features,
                hard_fail_reasons, suspicious_reasons, triggered_thresholds, frames=frames,
                scores=scores, pass_probability=pass_probability, failure_modes=vlm["failure_modes"], vlm=vlm_log,
            )

        return self._result(
            episode_id, "UNCERTAIN", False, confidence, "medium", vlm["reason"], features,
            hard_fail_reasons, suspicious_reasons, triggered_thresholds, frames=frames,
            scores=scores, pass_probability=pass_probability, failure_modes=vlm["failure_modes"], vlm=vlm_log,
        )

    def _result(
        self,
        episode_id: str,
        decision: str,
        should_submit: bool,
        confidence: float,
        risk_level: str,
        reason: str,
        features: dict[str, Any],
        hard_fail_reasons: list[str],
        suspicious_reasons: list[str],
        triggered_thresholds: list[dict[str, Any]],
        frames: dict[str, list[str]] | None = None,
        scores: dict[str, int] | None = None,
        pass_probability: float | None = None,
        failure_modes: list[str] | None = None,
        vlm: dict[str, Any] | None = None,
        error: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "episode_id": episode_id,
            "decision": decision,
            "should_submit": bool(should_submit),
            "confidence": confidence,
            "risk_level": risk_level,
            "scores": scores or self.config["default_scores"]["uncertain"],
            "reason": reason,
            "hard_fail_reasons": hard_fail_reasons,
            "suspicious_reasons": suspicious_reasons,
            "failure_modes": failure_modes or [],
            "pass_probability": pass_probability,
            "vlm_used": bool(vlm and vlm.get("used")),
            "form_plan": self._build_form_plan(
                decision,
                scores or self.config["default_scores"]["uncertain"],
                hard_fail_reasons,
                suspicious_reasons,
                failure_modes or [],
                pass_probability,
            ),
            "features": features,
            "rules": {
                "hard_fail_reasons": hard_fail_reasons,
                "suspicious_reasons": suspicious_reasons,
                "triggered_thresholds": triggered_thresholds,
            },
            "frames": frames or {},
            "vlm": vlm or {"used": False, "model": None, "prompt_version": None, "raw_output": None},
            "error": error,
        }

    def _build_form_plan(
        self,
        decision: str,
        scores: dict[str, int],
        hard_fail_reasons: list[str],
        suspicious_reasons: list[str],
        failure_modes: list[str],
        pass_probability: float | None,
    ) -> dict[str, Any]:
        form_cfg = self.config.get("form", {})
        selectors = self.config.get("browser", {}).get("selectors", {})
        pass_fail_items = form_cfg.get("pass_fail_items", {})
        slider_cfg = form_cfg.get("quality_sliders", {})
        slider_labels = form_cfg.get("slider_labels", {})

        all_reasons = hard_fail_reasons + suspicious_reasons + failure_modes
        normalized_reasons = [str(reason).lower() for reason in all_reasons]
        checks: dict[str, Any] = {}

        for key, item in pass_fail_items.items():
            value = None
            matched: list[str] = []
            if decision == "PASS":
                value = True
            elif decision == "FAIL":
                fail_modes = [str(mode).lower() for mode in item.get("fail_modes", [])]
                for mode in fail_modes:
                    if any(mode in reason for reason in normalized_reasons):
                        matched.append(mode)
                value = False if matched else True
            checks[key] = {
                "label": item.get("label", key),
                "value": value,
                "matched_fail_modes": sorted(set(matched)),
            }

        if decision == "FAIL" and checks and all(item["value"] is True for item in checks.values()):
            first_key = next(iter(checks))
            checks[first_key]["value"] = False
            checks[first_key]["matched_fail_modes"] = ["generic_fail"]

        sliders: dict[str, Any] = {}
        for score_key, cfg in slider_cfg.items():
            value = int(scores.get(score_key, 3))
            value = max(1, min(5, value))
            sliders[score_key] = {
                "label": cfg.get("label", score_key),
                "order": cfg.get("order"),
                "value": value,
                "level": slider_labels.get(value, str(value)),
            }

        gate_score = None
        if pass_probability is not None:
            gate_score = round(max(0.0, min(1.0, float(pass_probability))) * 100)
        elif decision == "PASS":
            gate_score = 100
        elif decision == "FAIL":
            gate_score = 0

        return {
            "can_fill": decision in {"PASS", "FAIL"},
            "can_submit": decision in {"PASS", "FAIL"},
            "submit_selector": selectors.get("submit_button"),
            "form_grid_table": selectors.get("form_grid_table"),
            "form_cell": selectors.get("form_cell"),
            "form_dot": selectors.get("form_dot"),
            "click_method": self.config.get("browser", {}).get("click_method", "react_dot"),
            "click_events": self.config.get("browser", {}).get("click_events", ["mousedown", "mouseup", "click"]),
            "pass_fail_checks": checks,
            "quality_sliders": sliders,
            "gate_score": gate_score,
        }
