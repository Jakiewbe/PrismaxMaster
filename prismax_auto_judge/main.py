from __future__ import annotations

import argparse
import time
from pathlib import Path
from typing import Any

from config_loader import load_config, resolve_data_path
from control_adapter import PrismaXControlAdapter, iter_local_episodes
from judge_logger import JsonlLogger
from processed_registry import ProcessedRegistry
from scorer import PrismaXScorer
from schemas import validate_vlm_output
from workflow_policy import DailyWorkflowPolicy


VALID_MODES = {"dry_run", "assist_preview", "assist_fill", "auto", "auto_limited"}


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

    if mode in {"auto", "auto_limited"}:
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



def make_control_record(mode: str) -> dict[str, Any]:
    return {
        "submitted": False,
        "submit_status": mode,
        "page_episode_id_before_submit": None,
        "page_episode_id_after_submit": None,
    }


def score_captured_episode(scorer: PrismaXScorer, episode: dict[str, Any]) -> dict[str, Any]:
    episode_id = str(episode.get("episode_id", "unknown"))
    frames = episode.get("frame_paths") or {}
    features = {
        "_aggregate": {
            "black_frame_ratio": 0.0,
            "freeze_ratio": 0.0,
            "motion_energy": 1.0,
            "brightness_mean": 100.0,
            "blur_score": 50.0,
        }
    }
    vlm_raw = scorer.vlm.judge_episode(
        task_prompt=str(episode.get("task_prompt", "")),
        frame_paths=frames,
        video_paths=episode.get("video_sources") or {},
        features=features,
        episode_id=episode_id,
    )
    if vlm_raw is None:
        return scorer._result(
            episode_id,
            "UNCERTAIN",
            False,
            0.50,
            "medium",
            "No VLM configured; live page captured frames only.",
            features,
            [],
            [],
            [],
            frames=frames,
            vlm={"used": False, "model": None, "prompt_version": None, "raw_output": None},
        )
    valid, vlm, validation_errors = validate_vlm_output(vlm_raw)
    if not valid or vlm is None:
        return scorer._result(
            episode_id,
            "UNCERTAIN",
            False,
            0.0,
            "high",
            "Invalid VLM output.",
            features,
            [],
            [],
            [],
            frames=frames,
            vlm={"used": True, "model": scorer.vlm.model_name, "prompt_version": scorer.vlm.prompt_version, "raw_output": vlm_raw},
            error={"vlm_validation_errors": validation_errors},
        )
    return scorer._decide_from_vlm(episode_id, features, [], [], [], frames, vlm)


def apply_live_mode(
    adapter: PrismaXControlAdapter,
    result: dict[str, Any],
    mode: str,
    config: dict[str, Any],
    auto_submit_count: int,
) -> tuple[dict[str, Any], int]:
    control_record = make_control_record(mode)
    if mode in {"dry_run", "assist_preview"}:
        control_record["submit_status"] = mode
        return control_record, auto_submit_count

    if mode == "assist_fill":
        adapter.fill_result(result)
        control_record["submit_status"] = "filled_not_submitted"
        return control_record, auto_submit_count

    if mode in {"auto", "auto_limited"}:
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
        before_id = adapter.get_episode_id()
        control_record["page_episode_id_before_submit"] = before_id
        if safety.get("require_episode_id_match_before_submit", True) and before_id != result.get("episode_id"):
            adapter.abort_submit("episode_id changed")
        adapter.fill_result(result)
        adapter.submit()
        control_record["submitted"] = True
        control_record["submit_status"] = "submitted"
        control_record["page_episode_id_after_submit"] = adapter.get_episode_id()
        return control_record, auto_submit_count

    control_record["submit_status"] = "unknown_mode"
    return control_record, auto_submit_count



def print_capture_summary(episode: dict[str, Any]) -> None:
    frame_paths = episode.get("frame_paths", {})
    errors = episode.get("metadata", {}).get("capture_errors", [])
    total = sum(len(paths) for paths in frame_paths.values())
    print(f"capture_summary: frames={total} errors={len(errors)}")
    for view, paths in frame_paths.items():
        print(f"  {view}: {len(paths)} frames")
    black_errors = [err for err in errors if "black_or_not_ready" in str(err)]
    if black_errors:
        print(f"  black_or_not_ready_errors={len(black_errors)}")


def _set_vla_state(vla_active: bool, state_path: str = "../prismax_state.json") -> bool:
    """Write vlaActive flag so the extension can pause/resume control loop.
    Returns True if handshake succeeded (extension acknowledged by writing
    controlPausedForVla back), or if state file doesn't exist yet (first run).
    """
    import json
    path = Path(__file__).resolve().parent / state_path
    state: dict[str, Any] = {}
    if path.exists():
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass
    state["vlaActive"] = vla_active
    state["vlaStateUpdatedAt"] = time.strftime("%Y-%m-%d %H:%M:%S")
    if not vla_active:
        state.pop("controlPausedForVla", None)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    # Handshake: wait for extension to ack (max 5s)
    if vla_active:
        import time as _time
        deadline = _time.monotonic() + 5.0
        while _time.monotonic() < deadline:
            try:
                current = json.loads(path.read_text(encoding="utf-8"))
                if current.get("controlPausedForVla"):
                    return True
            except (OSError, json.JSONDecodeError):
                pass
            _time.sleep(0.3)
        return False  # extension didn't ack in time
    return True


def run_live_once(
    config: dict[str, Any],
    config_hash: str,
    step: str,
    return_arm: bool = False,
) -> int:
    runtime = config["runtime"]
    mode = runtime.get("mode", "dry_run")
    workflow = DailyWorkflowPolicy(config, Path(__file__).resolve().parent)
    allowed, reason = workflow.can_attempt_vla()
    print(f"workflow: {reason}")
    if step == "workflow":
        return 0 if allowed else 2
    readonly_steps = {"open-review", "open-first", "capture", "score", "fill", "return-arm"}
    if not allowed and step not in readonly_steps:
        return 2

    adapter = PrismaXControlAdapter(config)
    logger = JsonlLogger(resolve_data_path(runtime["log_path"]))
    scorer = PrismaXScorer(config, config_hash)
    auto_submit_count = 0
    try:
        _set_vla_state(True)
        adapter.open_page()
        if step == "return-arm":
            ok = adapter.return_to_arm_queue()
            print(f"return_to_arm_queue: {ok}")
            return 0 if ok else 3
        if step == "open-review":
            print("review list opened")
            return 0
        if not adapter.open_first_review():
            raise RuntimeError("No Review & Earn item opened")
        print(f"review opened: {adapter.get_current_episode()}")
        if step == "open-first":
            return 0
        episode = adapter.capture_current_episode_frames()
        print_capture_summary(episode)
        if step == "capture":
            return 0
        result = score_captured_episode(scorer, episode)
        control_record = make_control_record(mode)
        if step in {"fill", "submit", "full"}:
            active_mode = mode
            if step == "fill" and active_mode == "assist_preview":
                active_mode = "assist_fill"
            if step == "submit" and active_mode not in {"auto", "auto_limited"}:
                raise RuntimeError("submit step requires runtime.mode auto or auto_limited")
            control_record, auto_submit_count = apply_live_mode(adapter, result, active_mode, config, auto_submit_count)
            workflow.record_vla_result(bool(control_record.get("submitted")))
        logger.write(build_log_record(episode, result, mode, config_hash, scorer.version, control_record))
        print(f"result: {result['decision']} submit={control_record['submitted']} status={control_record['submit_status']}")
        if return_arm or step == "return-arm" or (step == "full" and config.get("post_vla", {}).get("return_to_arm_queue", True)):
            ok = adapter.return_to_arm_queue()
            print(f"return_to_arm_queue: {ok}")
            return 0 if ok else 3
        return 0
    finally:
        _set_vla_state(False)
        adapter.close()


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
    workflow = DailyWorkflowPolicy(config, Path(__file__).resolve().parent)

    processed_count = 0
    auto_submit_count = 0
    for episode in iter_local_episodes(video_root):
        allowed, workflow_reason = workflow.can_attempt_vla()
        if not allowed:
            print(f"VLA blocked by workflow policy: {workflow_reason}")
            break

        episode_id = str(episode["episode_id"])
        if registry.is_submitted(episode_id):
            continue
        result = scorer.score_episode(episode)
        control_record, auto_submit_count = apply_local_mode(result, mode, config, auto_submit_count)
        logger.write(build_log_record(episode, result, mode, config_hash, scorer.version, control_record))
        registry.mark(episode_id, str(result.get("decision")), bool(control_record.get("submitted")))
        workflow.record_vla_result(bool(control_record.get("submitted")))
        processed_count += 1
        print(f"{episode_id}: {result['decision']} submit={control_record['submitted']} reason={result['reason']}")
        if mode in {"auto", "auto_limited"} and control_record.get("submitted"):
            auto_submit_count += 1
            time.sleep(float(config.get("safety", {}).get("submit_cooldown_seconds", 2)))

    if processed_count == 0:
        print(f"No local videos found in {video_root}")
    return processed_count


def main() -> int:
    parser = argparse.ArgumentParser(description="PrismaX VLA auto judge")
    parser.add_argument("--config", default=None, help="Path to config.yaml")
    parser.add_argument("--video-dir", default=None, help="Local video folder for dry-run batch")
    parser.add_argument("--live-step", choices=["workflow", "open-review", "open-first", "capture", "score", "fill", "submit", "return-arm", "full"], default=None, help="Run one testable live-browser step")
    parser.add_argument("--return-arm", action="store_true", help="After the live step, return to configured arm queue")
    args = parser.parse_args()

    config, config_hash = load_config(args.config)
    if args.live_step:
        return run_live_once(config, config_hash, args.live_step, args.return_arm)
    run_local_batch(config, config_hash, args.video_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
