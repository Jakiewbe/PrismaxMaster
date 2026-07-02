from __future__ import annotations

import json
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen

from config_loader import load_config
from workflow_policy import DailyWorkflowPolicy


ROOT_DIR = Path(__file__).resolve().parents[1]
AUTO_DIR = Path(__file__).resolve().parent
STATE_PATH = AUTO_DIR / "data" / "logs" / "vla_scheduler_state.json"
HEARTBEAT_PATH = AUTO_DIR / "data" / "logs" / "vla_scheduler_heartbeat.json"
LOG_PATH = ROOT_DIR / "logs" / "vla_scheduler.log"
BRIDGE_STATE_URL = "http://127.0.0.1:5000/state"
CONTROL_STATE_PATH = ROOT_DIR / "prismax_state.json"


@dataclass(frozen=True)
class TriggerDecision:
    should_run: bool
    reason: str
    force_workflow: bool = False


def today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def now_ts() -> float:
    return time.time()


def log(message: str) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}"
    print(line, flush=True)
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def read_json(path: Path) -> dict[str, Any]:
    try:
        if not path.exists():
            return {}
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def fetch_control_state() -> dict[str, Any]:
    try:
        with urlopen(BRIDGE_STATE_URL, timeout=2) as response:
            data = json.loads(response.read().decode("utf-8"))
            state = data.get("data", data)
            if isinstance(state, dict):
                return state
    except (OSError, URLError, TimeoutError, json.JSONDecodeError):
        pass
    return read_json(CONTROL_STATE_PATH)


def control_count(state: dict[str, Any]) -> int:
    for key in ("todayControlSuccessCount", "totalOperations", "count"):
        if key not in state or state.get(key) is None:
            continue
        try:
            return int(state.get(key) or 0)
        except (TypeError, ValueError):
            continue
    return 0


def control_is_busy(state: dict[str, Any]) -> tuple[bool, str]:
    if bool(state.get("isOperating")):
        return True, "operating"
    if bool(state.get("walletPopupActive")):
        return True, "wallet_popup"
    owner = state.get("actionLockOwner")
    if owner:
        return True, f"action_lock:{owner}"
    return False, "not_busy"


def refresh_scheduler_state(scheduler_state: dict[str, Any], control_state: dict[str, Any], now: float) -> dict[str, Any]:
    current_day = today()
    current_count = control_count(control_state)
    if scheduler_state.get("date") != current_day:
        scheduler_state = {
            "date": current_day,
            "baseline_control_count": current_count,
            "last_control_count": current_count,
            "last_control_change_at": now,
            "last_vla_attempt_at": 0,
        }
        return scheduler_state

    if "baseline_control_count" not in scheduler_state:
        scheduler_state["baseline_control_count"] = current_count
    if "last_control_change_at" not in scheduler_state:
        scheduler_state["last_control_change_at"] = now
    if int(scheduler_state.get("last_control_count", current_count) or 0) != current_count:
        scheduler_state["last_control_count"] = current_count
        scheduler_state["last_control_change_at"] = now
    return scheduler_state


def control_delta(scheduler_state: dict[str, Any], control_state: dict[str, Any]) -> int:
    return max(0, control_count(control_state) - int(scheduler_state.get("baseline_control_count", 0) or 0))


def decide_vla_trigger(
    config: dict[str, Any],
    workflow: DailyWorkflowPolicy,
    control_state: dict[str, Any],
    scheduler_state: dict[str, Any],
    now: float,
) -> TriggerDecision:
    workflow_cfg = config.get("daily_workflow", {})
    if not workflow_cfg.get("auto_vla_scheduler_enabled", True):
        return TriggerDecision(False, "scheduler_disabled")

    max_tasks = int(workflow_cfg.get("max_vla_tasks_per_day", workflow_cfg.get("min_vla_tasks_per_day", 1)))
    tasks_done = workflow.get_today_task_count()
    if tasks_done >= max_tasks:
        return TriggerDecision(False, f"daily_task_quota_done:{tasks_done}/{max_tasks}")

    last_attempt = float(scheduler_state.get("last_vla_attempt_at", 0) or 0)
    retry_seconds = int(workflow_cfg.get("vla_retry_cooldown_minutes", 30)) * 60
    if last_attempt and now - last_attempt < retry_seconds:
        return TriggerDecision(False, "retry_cooldown")

    busy, busy_reason = control_is_busy(control_state)
    if busy:
        return TriggerDecision(False, f"control_busy:{busy_reason}")

    min_ops = int(workflow_cfg.get("min_control_operations_before_vla", 6))
    delta = control_delta(scheduler_state, control_state)
    if delta >= min_ops:
        return TriggerDecision(True, f"control_ops_ready:{delta}/{min_ops}", force_workflow=True)

    if workflow_cfg.get("allow_vla_when_control_stalled", True):
        stalled_for = now - float(scheduler_state.get("last_control_change_at", now) or now)
        stall_seconds = int(workflow_cfg.get("control_stall_minutes_before_vla", 30)) * 60
        if stalled_for >= stall_seconds:
            return TriggerDecision(True, f"control_stalled:{int(stalled_for)}s", force_workflow=True)

    allowed, reason = workflow.can_attempt_vla()
    if allowed:
        return TriggerDecision(True, reason, force_workflow=False)
    return TriggerDecision(False, reason)


def run_vla_full(force_workflow: bool) -> int:
    cmd = [sys.executable, str(AUTO_DIR / "main.py"), "--live-step", "full"]
    if force_workflow:
        cmd.append("--force-workflow")
    log("starting VLA: " + " ".join(cmd))
    completed = subprocess.run(cmd, cwd=str(AUTO_DIR), text=True)
    return int(completed.returncode)


def write_heartbeat(decision: TriggerDecision, control_state: dict[str, Any], scheduler_state: dict[str, Any]) -> None:
    write_json(
        HEARTBEAT_PATH,
        {
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "decision": decision.reason,
            "should_run": decision.should_run,
            "force_workflow": decision.force_workflow,
            "control_count": control_count(control_state),
            "control_delta": control_delta(scheduler_state, control_state),
            "is_operating": bool(control_state.get("isOperating")),
            "is_queuing": bool(control_state.get("isQueuing")),
        },
    )


def main() -> int:
    config, _config_hash = load_config(None)
    workflow = DailyWorkflowPolicy(config, AUTO_DIR)
    workflow_cfg = config.get("daily_workflow", {})
    poll_seconds = max(3, int(workflow_cfg.get("vla_trigger_poll_seconds", 10)))
    log("VLA scheduler starting")

    while True:
        loop_now = now_ts()
        scheduler_state = read_json(STATE_PATH)
        control_state = fetch_control_state()
        scheduler_state = refresh_scheduler_state(scheduler_state, control_state, loop_now)
        decision = decide_vla_trigger(config, workflow, control_state, scheduler_state, loop_now)
        write_heartbeat(decision, control_state, scheduler_state)

        if decision.should_run:
            scheduler_state["last_vla_attempt_at"] = loop_now
            write_json(STATE_PATH, scheduler_state)
            code = run_vla_full(decision.force_workflow)
            log(f"VLA finished with code={code}")
        else:
            write_json(STATE_PATH, scheduler_state)

        time.sleep(poll_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
