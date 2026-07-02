from __future__ import annotations

import argparse
import copy
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


def force_live_submit_result(
    scorer: PrismaXScorer,
    result: dict[str, Any],
    config: dict[str, Any],
) -> dict[str, Any]:
    """Make live VLA output submittable; uncertain/low confidence becomes PASS."""
    if not config.get("safety", {}).get("force_submit_live_vla", False):
        return result

    safety = config.get("safety", {})
    decision = str(result.get("decision") or "UNCERTAIN")
    should_submit = bool(result.get("should_submit"))
    confidence = float(result.get("confidence") or 0.0)
    pass_probability = result.get("pass_probability")
    pass_probability_value = float(pass_probability) if pass_probability is not None else 0.50

    strict_fail = (
        decision == "FAIL"
        and confidence >= float(safety.get("strict_fail_submit_min_confidence", 0.90))
        and pass_probability_value <= float(safety.get("strict_fail_submit_max_pass_probability", 0.10))
    )
    forced_decision = "FAIL" if strict_fail else "PASS"

    if forced_decision == decision and should_submit:
        return result

    reason = str(result.get("reason") or "")
    force_reason = "Forced live VLA submit policy: uncertain, low-confidence, or non-strict FAIL output is submitted as PASS."
    if forced_decision == "FAIL":
        force_reason = "Forced live VLA submit policy: high-confidence FAIL is submitted instead of blocked."
    if reason:
        reason = reason + " " + force_reason
    else:
        reason = force_reason

    rules = result.get("rules") or {}
    return scorer._result(
        str(result.get("episode_id") or "unknown"),
        forced_decision,
        True,
        float(result.get("confidence") or 0.0),
        str(result.get("risk_level") or "medium"),
        reason,
        result.get("features") or {},
        list(result.get("hard_fail_reasons") or rules.get("hard_fail_reasons") or []),
        list(result.get("suspicious_reasons") or rules.get("suspicious_reasons") or []),
        list(rules.get("triggered_thresholds") or []),
        frames=result.get("frames") or {},
        scores=result.get("scores") or config["default_scores"]["uncertain"],
        pass_probability=pass_probability_value,
        failure_modes=result.get("failure_modes") or [],
        vlm=result.get("vlm"),
        error=result.get("error"),
    )


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
        force_submit = bool(safety.get("force_submit_live_vla", False))
        if result.get("decision") == "FAIL" and not safety.get("allow_auto_fail_submit", False) and not force_submit:
            control_record["submit_status"] = "auto_fail_submit_disabled"
            return control_record, auto_submit_count
        if not result.get("should_submit") and not force_submit:
            control_record["submit_status"] = "not_submittable"
            return control_record, auto_submit_count
        if auto_submit_count >= int(safety.get("max_auto_submit_per_run", 10)):
            control_record["submit_status"] = "max_auto_submit_per_run_reached"
            return control_record, auto_submit_count
        result_episode_id = str(result.get("episode_id") or "")
        before_id = adapter.get_episode_id()
        control_record["page_episode_id_before_submit"] = before_id
        if safety.get("require_episode_id_match_before_submit", True) and result_episode_id and before_id and before_id != result_episode_id:
            adapter.abort_submit(f"episode_id changed: page={before_id} vs result={result_episode_id}")
        adapter.fill_result(result)
        adapter.submit()
        control_record["submitted"] = True
        control_record["submit_status"] = "submitted"
        control_record["page_episode_id_after_submit"] = adapter.get_episode_id()
        if hasattr(adapter, "increment_vla_submitted_today"):
            control_record["browser_today_vla_submitted_updated"] = adapter.increment_vla_submitted_today()
        auto_submit_count += 1
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


def _set_vla_state(vla_active: bool, state_path: str = "../prismax_state.json", control_paused: bool | None = None) -> bool:
    """Write VLA ownership state for external monitors."""
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
    if control_paused is not None:
        state["controlPausedForVla"] = bool(control_paused)
    elif not vla_active:
        state.pop("controlPausedForVla", None)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    return True


def _progress_value(info: dict[str, Any] | None, key: str, default: int) -> int:
    progress = (info or {}).get("progress") or {}
    try:
        return int(progress.get(key, default) or default)
    except (TypeError, ValueError):
        return default


def _same_episode(left: dict[str, Any] | None, right: dict[str, Any] | None) -> bool:
    if not left or not right:
        return False
    return str(left.get("episode_id") or "") == str(right.get("episode_id") or "")


def run_live_episode(
    adapter: PrismaXControlAdapter,
    scorer: PrismaXScorer,
    logger: JsonlLogger,
    workflow: DailyWorkflowPolicy,
    config: dict[str, Any],
    config_hash: str,
    mode: str,
    step: str,
    auto_submit_count: int,
) -> tuple[bool, int, dict[str, Any]]:
    """Process the current review episode and report whether the task has more episodes."""
    current = adapter.get_current_episode()
    if not current or not current.get("task_id"):
        if not adapter.open_first_review():
            raise RuntimeError("No Review & Earn item opened")
        current = adapter.get_current_episode()
    print(f"review opened: {current}")
    if step == "open-first":
        return False, auto_submit_count, make_control_record(mode)

    episode = adapter.capture_current_episode_frames()
    print_capture_summary(episode)
    if step == "capture":
        return False, auto_submit_count, make_control_record(mode)

    result = force_live_submit_result(scorer, score_captured_episode(scorer, episode), config)
    control_record = make_control_record(mode)
    control_record["task_progress_before"] = (current or {}).get("progress")
    if step in {"fill", "submit", "full"}:
        active_mode = mode
        if step == "fill" and active_mode == "assist_preview":
            active_mode = "assist_fill"
        if step == "submit" and active_mode not in {"auto", "auto_limited"}:
            raise RuntimeError("submit step requires runtime.mode auto or auto_limited")
        control_record, auto_submit_count = apply_live_mode(adapter, result, active_mode, config, auto_submit_count)
        control_record["task_progress_before"] = (current or {}).get("progress")
        workflow.record_vla_result(bool(control_record.get("submitted")))

    after = adapter.get_current_episode()
    control_record["task_progress_after"] = (after or {}).get("progress")
    logger.write(build_log_record(episode, result, mode, config_hash, scorer.version, control_record))
    print(f"result: {result['decision']} submit={control_record['submitted']} status={control_record['submit_status']}")

    if step not in {"full", "fill"}:
        return False, auto_submit_count, control_record
    if step == "full" and not control_record.get("submitted"):
        return False, auto_submit_count, control_record

    total = _progress_value(current, "total", 1)
    before_current = _progress_value(current, "current", 1)
    after_current = _progress_value(after, "current", before_current)
    return max(before_current, after_current) < total, auto_submit_count, control_record


def run_live_task(
    adapter: PrismaXControlAdapter,
    scorer: PrismaXScorer,
    logger: JsonlLogger,
    workflow: DailyWorkflowPolicy,
    config: dict[str, Any],
    config_hash: str,
    mode: str,
    step: str,
    auto_submit_count: int,
) -> tuple[int, int, int]:
    """Run one VLA task, where one task can contain many review episodes."""
    if not adapter.open_first_review():
        raise RuntimeError("No Review & Earn item opened")

    first = adapter.get_current_episode() or {}
    workflow_cfg = config.get("daily_workflow", {})
    max_episodes = int(workflow_cfg.get("max_episodes_per_task", 20))
    episodes_seen = 0
    episodes_submitted = 0
    completed = False

    while episodes_seen < max_episodes:
        allowed, reason = workflow.can_attempt_vla()
        print(f"workflow_task_loop: {reason}")
        if not allowed:
            break

        before = adapter.get_current_episode()
        should_continue, auto_submit_count, control_record = run_live_episode(
            adapter, scorer, logger, workflow, config, config_hash, mode, step, auto_submit_count
        )
        episodes_seen += 1
        if control_record.get("submitted"):
            episodes_submitted += 1

        if not should_continue:
            completed = True
            break

        after = adapter.get_current_episode()
        if _same_episode(before, after):
            adapter.next_episode()

    workflow.record_vla_task_result(completed or episodes_seen > 0, episodes_seen, episodes_submitted)
    task_id = first.get("task_id") or "unknown"
    print(f"task_result: task_id={task_id} episodes={episodes_seen} submitted={episodes_submitted} completed={completed}")
    return episodes_seen, episodes_submitted, auto_submit_count


def run_live_once(
    config: dict[str, Any],
    config_hash: str,
    step: str,
    return_arm: bool = False,
    force_workflow: bool = False,
) -> int:
    if force_workflow:
        config = copy.deepcopy(config)
        config.setdefault("daily_workflow", {})["control_first"] = False
    runtime = config["runtime"]
    mode = runtime.get("mode", "dry_run")
    workflow = DailyWorkflowPolicy(config, Path(__file__).resolve().parent)
    allowed, reason = workflow.can_attempt_vla()
    print(f"workflow: {reason}" + (" (forced)" if force_workflow else ""))
    if step == "workflow":
        return 0 if allowed else 2
    readonly_steps = {"return-arm", "open-review", "open-first", "capture", "score", "fill"}
    if not allowed and step not in readonly_steps:
        return 2

    adapter = PrismaXControlAdapter(config)
    logger = JsonlLogger(resolve_data_path(runtime["log_path"]))
    scorer = PrismaXScorer(config, config_hash)
    auto_submit_count = 0
    control_pause_active = False
    try:
        adapter.open_page(open_review=step != "return-arm")
        if step != "return-arm":
            control_pause_active = adapter.set_vla_control_pause(True)
            _set_vla_state(True, control_paused=control_pause_active)
            if not control_pause_active and config.get("safety", {}).get("require_extension_pause_for_vla", True):
                raise RuntimeError("extension_control_pause_not_acknowledged")
        if step == "return-arm":
            ok = adapter.return_to_arm_queue()
            print(f"return_to_arm_queue: {ok}")
            return 0 if ok else 3
        if step == "open-review":
            print("review list opened")
            return 0

        if step in {"full", "fill"}:
            workflow_cfg = config.get("daily_workflow", {})
            min_tasks = int(workflow_cfg.get("min_vla_tasks_per_day", 1))
            max_tasks = int(workflow_cfg.get("max_vla_tasks_per_day", min_tasks))
            processed_tasks = 0
            processed_episodes = 0
            while processed_tasks < max_tasks:
                allowed, reason = workflow.can_attempt_vla()
                print(f"workflow_loop: {reason}")
                if not allowed:
                    break
                if processed_tasks >= min_tasks:
                    break
                episodes_seen, _episodes_submitted, auto_submit_count = run_live_task(
                    adapter, scorer, logger, workflow, config, config_hash, mode, step, auto_submit_count
                )
                if episodes_seen <= 0:
                    break
                processed_tasks += 1
                processed_episodes += episodes_seen
                if processed_tasks < min_tasks:
                    adapter.open_page(open_review=True)
            if config.get("post_vla", {}).get("return_to_arm_queue", True):
                ok = adapter.return_to_arm_queue()
                print(f"return_to_arm_queue: {ok}")
                return 0 if ok else 3
            return 0 if processed_episodes > 0 else 2

        should_continue, auto_submit_count, control_record = run_live_episode(
            adapter, scorer, logger, workflow, config, config_hash, mode, step, auto_submit_count
        )
        if return_arm:
            ok = adapter.return_to_arm_queue()
            print(f"return_to_arm_queue: {ok}")
            return 0 if ok else 3
        return 0
    finally:
        if control_pause_active:
            try:
                adapter.set_vla_control_pause(False)
            except Exception:
                pass
        _set_vla_state(False, control_paused=False)
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
    parser.add_argument("--force-workflow", action="store_true", help="Bypass the control-first gate; daily VLA task quota still applies")
    args = parser.parse_args()

    config, config_hash = load_config(args.config)
    if args.live_step:
        return run_live_once(config, config_hash, args.live_step, args.return_arm, args.force_workflow)
    run_local_batch(config, config_hash, args.video_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

