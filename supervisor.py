"""
PRISMAX local supervisor.

Starts Bridge and Python controller once, then monitors health.
It only reports alerts; it does not refresh the browser or restart processes.
"""

import json
import os
import subprocess
import sys
import time
from datetime import datetime
from urllib.error import URLError
from urllib.request import urlopen

from config_shared import (
    BRIDGE_HOST,
    BRIDGE_PORT,
    PYTHON_HEARTBEAT_FILE,
    SUPERVISOR_POLL_SECONDS,
)


ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
BRIDGE_SCRIPT = os.path.join(ROOT_DIR, "Bridge_v2.py")
BOT_SCRIPT = os.path.join(ROOT_DIR, "prismax_bot_v2.5_crossplatform.py")
VLA_SCHEDULER_SCRIPT = os.path.join(ROOT_DIR, "prismax_auto_judge", "daily_orchestrator.py")
HEALTH_URL = f"http://{BRIDGE_HOST}:{BRIDGE_PORT}/health"
LOG_DIR = os.path.join(ROOT_DIR, "logs")
SUMMARY_INTERVAL_SECONDS = 60


def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def log(message):
    print(f"[{now_str()}] {message}", flush=True)


def start_process(script_path, name):
    if not os.path.exists(script_path):
        log(f"[ERROR] {name} script not found: {script_path}")
        return None
    log(f"[START] {name}: {os.path.basename(script_path)}")
    os.makedirs(LOG_DIR, exist_ok=True)
    log_name = name.lower().replace(" ", "_")
    log_path = os.path.join(LOG_DIR, f"supervisor_{log_name}.log")
    log(f"[LOG] {name} output -> {log_path}")
    log_file = open(log_path, "a", encoding="utf-8", buffering=1)
    log_file.write(f"\n\n[{now_str()}] supervisor started {name}\n")
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    return subprocess.Popen(
        [sys.executable, script_path],
        cwd=ROOT_DIR,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        env=env,
    )


def read_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def fetch_health():
    try:
        with urlopen(HEALTH_URL, timeout=2) as response:
            return json.loads(response.read().decode("utf-8"))
    except (URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        return {"bridge_alive": False, "error": str(exc)}


def summarize_health(health):
    if not health.get("bridge_alive"):
        return "Bridge 异常"

    js_status = health.get("js_status", "missing")
    python_status = health.get("python_status", "missing")
    perf_mode = health.get("performance_mode", "unknown")

    parts = [f"Bridge 正常", f"JS={js_status}", f"Python={python_status}", f"mode={perf_mode}"]
    if health.get("js_heartbeat_age") is not None:
        parts.append(f"JS心跳={health['js_heartbeat_age']}s")
    if health.get("python_heartbeat_age") is not None:
        parts.append(f"Py心跳={health['python_heartbeat_age']}s")
    return " | ".join(parts)


def health_state_key(health):
    if not health.get("bridge_alive"):
        return ("bridge_down",)
    return (
        health.get("js_status", "missing"),
        health.get("python_status", "missing"),
        health.get("performance_mode", "unknown"),
        bool(health.get("allow_operation")),
    )


def alert_key(health, bridge_proc, bot_proc, vla_proc):
    keys = []
    if not health.get("bridge_alive"):
        keys.append("bridge_down")
    elif health.get("js_status") in ("missing", "stale"):
        keys.append(f"js_{health.get('js_status')}")
    if health.get("python_status") in ("missing", "stale", "error"):
        keys.append(f"python_{health.get('python_status')}")
    if bridge_proc and bridge_proc.poll() is not None and not health.get("bridge_alive"):
        keys.append("bridge_process_exited")
    if bot_proc and bot_proc.poll() is not None:
        keys.append("bot_process_exited")
    if vla_proc and vla_proc.poll() is not None:
        keys.append("vla_scheduler_exited")
    return tuple(keys)


def main():
    log("PRISMAX supervisor starting")
    log("Policy: alert only; no browser refresh and no automatic restart.")

    bridge_proc = start_process(BRIDGE_SCRIPT, "Bridge")
    time.sleep(1)
    bot_proc = start_process(BOT_SCRIPT, "Python controller")
    vla_proc = start_process(VLA_SCHEDULER_SCRIPT, "VLA scheduler")

    last_alert = None
    last_state = None
    last_summary_at = 0

    try:
        while True:
            health = fetch_health()
            heartbeat = read_json(os.path.join(ROOT_DIR, PYTHON_HEARTBEAT_FILE))
            summary = summarize_health(health)
            state_key = health_state_key(health)
            current_alert = alert_key(health, bridge_proc, bot_proc, vla_proc)

            should_print_summary = (
                state_key != last_state
                or time.time() - last_summary_at >= SUMMARY_INTERVAL_SECONDS
            )
            if should_print_summary:
                log(summary)
                last_state = state_key
                last_summary_at = time.time()

            if current_alert and current_alert != last_alert:
                log(f"[ALERT] {'; '.join(current_alert)}")
                if heartbeat and heartbeat.get("lastError"):
                    log(f"[PYTHON LAST ERROR] {heartbeat['lastError']}")
                if health.get("last_script_error"):
                    log(f"[JS LAST ERROR] {health['last_script_error']}")
                last_alert = current_alert
            elif not current_alert and last_alert:
                log("[RECOVERED] all monitored components look healthy")
                last_alert = None

            time.sleep(SUPERVISOR_POLL_SECONDS)
    except KeyboardInterrupt:
        log("Supervisor stopping by user request")


if __name__ == "__main__":
    main()
