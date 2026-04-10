#!/usr/bin/env python
"""
Cron-based performance observer for the metrics-service collection pipeline.

Unlike benchmark_api.py (which triggers collectors manually via the API), this
script observes the *production cron schedule* — exactly as Milan described:
collectors run every hour, each reading only the previous hour's window, to
avoid loading unbounded data into memory at once.

How it works
------------
1. Waits until just before the next scheduled cron run (XX:05 for
   job_host_summary_service by default).
2. Prints a countdown and a reminder of **which hour window** the next run will
   collect, so you know exactly when to generate AWX test data.
3. After the cron fires, polls the TaskExecution table via the API until the
   run completes.
4. Records started_at → completed_at as the authoritative wall-clock duration
   (same source of truth as benchmark_api.py).
5. Captures a Prometheus /metrics snapshot and saves everything to a JSON
   results file.

When should I generate host data?
----------------------------------
The cron at XX:05 collects the window [XX-1:00, XX:00).
Example: cron fires at 14:05 → window is 13:00–14:00.

So you must generate AWX jobs (via testathon) such that those jobs *finish*
within that previous-hour window. Since testathon generates jobs in near-real
time, the simplest approach is:

  1. Run this script — it will print the exact target window.
  2. Run testathon immediately. Jobs will finish within the current hour.
  3. Wait for the script to detect the next XX:05 cron tick and capture it.

If you miss the window (jobs finish after the hour boundary), run testathon
again during the next hour and let the script catch the following cron run.

Usage
-----
    BASE_URL=http://localhost:8006/api \\
    BENCHMARK_USER=admin \\
    PASSWORD=Admin!Password!Metrics \\
    METRICS_URL=http://localhost:8006/metrics \\
    DATA_SCALE=500_job_host_summaries \\
        python metrics_service/tools/performance_tests/benchmark_cron_observer.py

    # Override which cron minute to wait for (default 5 = XX:05):
    CRON_MINUTE=5 python ...

    # Run for multiple consecutive hours (e.g. 3 back-to-back cron runs):
    OBSERVE_RUNS=3 python ...

Environment variables
---------------------
    BASE_URL        metrics-service API base URL (default: http://localhost:8006/api)
    BENCHMARK_USER  Admin username              (default: admin)
    PASSWORD        Admin password              (default: Admin!Password!Metrics)
    METRICS_URL     Prometheus /metrics URL     (optional)
    DATA_SCALE      Short label, e.g. "500_job_host_summaries"
    RESULTS_DIR     Output directory            (default: ./results/ next to this script)
    CRON_MINUTE     Minute of hour to wait for  (default: 5, matching XX:05 cron)
    OBSERVE_RUNS    How many consecutive cron runs to capture (default: 1)
    POLL_INTERVAL   Seconds between task status polls (default: 2)
    POLL_TIMEOUT    Max seconds to wait for task completion (default: 600)
"""

# ruff: noqa: T201
import json
import os
import time
import datetime as dt
from datetime import timedelta

import requests
from requests.auth import HTTPBasicAuth

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BASE_URL = os.environ.get("BASE_URL", "http://localhost:8006/api").rstrip("/")
USERNAME = os.environ.get("BENCHMARK_USER", "admin")
PASSWORD = os.environ.get("PASSWORD", "")
METRICS_URL = os.environ.get("METRICS_URL", "")
DATA_SCALE = os.environ.get("DATA_SCALE", "")
RESULTS_DIR = os.environ.get("RESULTS_DIR", os.path.join(os.path.dirname(__file__), "..", "results"))
CRON_MINUTE = int(os.environ.get("CRON_MINUTE", "5"))   # XX:05 = job_host_summary cron
OBSERVE_RUNS = int(os.environ.get("OBSERVE_RUNS", "1"))
POLL_INTERVAL = float(os.environ.get("POLL_INTERVAL", "2"))
POLL_TIMEOUT = int(os.environ.get("POLL_TIMEOUT", "600"))

AUTH = HTTPBasicAuth(USERNAME, PASSWORD)

# Cron schedule from task_groups.py (for reference in printed output only)
CRON_SCHEDULE = {
    5:  "job_host_summary_service",
    10: "unified_jobs",
    15: "credentials_service",
}


# ---------------------------------------------------------------------------
# Time helpers
# ---------------------------------------------------------------------------

def next_cron_time(minute: int) -> dt.datetime:
    """Return the next UTC datetime when the clock hits HH:<minute>:00."""
    now = dt.datetime.now(dt.timezone.utc)
    candidate = now.replace(minute=minute, second=0, microsecond=0)
    if candidate <= now:
        candidate += timedelta(hours=1)
    return candidate


def collection_window_for_cron(cron_at: dt.datetime) -> tuple[dt.datetime, dt.datetime]:
    """
    Return the (since, until) window that the cron run at `cron_at` will collect.

    The default logic in collect_hourly_metrics.py is:
        hour_timestamp = now.replace(minute=0, ...) - timedelta(hours=1)
    So a cron firing at 14:05 yields window 13:00–14:00.
    """
    top_of_hour = cron_at.replace(minute=0, second=0, microsecond=0)
    since = top_of_hour - timedelta(hours=1)
    until = top_of_hour
    return since, until


def fmt(d: dt.datetime) -> str:
    return d.strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------

def latest_task_execution(collector_type: str, since: dt.datetime):
    """
    Return the most recent Task for `collector_type` whose `created`
    timestamp is >= `since`. Returns None if not found yet.

    Notes on the API:
    - `started_at` is always null on the Task list endpoint; use `created`
      (the enqueue/start time) instead.
    - `ordering` is not a supported filter; results default to newest-first.
    - Match collector_type via task_data.collector_type.
    """
    try:
        resp = requests.get(
            f"{BASE_URL}/v1/tasks/",
            params={"page_size": 20},
            auth=AUTH,
            timeout=10,
        )
        resp.raise_for_status()
    except Exception:
        return None

    for task in resp.json().get("results", []):
        task_data = task.get("task_data") or {}
        if task_data.get("collector_type") != collector_type:
            continue
        created_raw = task.get("created")
        if not created_raw:
            continue
        created_at = dt.datetime.fromisoformat(created_raw.replace("Z", "+00:00"))
        if created_at >= since:
            return task

    return None


def wait_for_cron_task(collector_type: str, cron_fired_at: dt.datetime) -> dict:
    """
    Wait until a TaskExecution for `collector_type` appears that was started
    after `cron_fired_at`, then wait until it reaches a terminal state.

    Returns the full task dict from the API.
    """
    # Give the dispatcher up to 2 minutes to pick up the cron task
    deadline = time.perf_counter() + POLL_TIMEOUT
    task = None

    print(f"  Waiting for dispatcherd to pick up {collector_type} task...", end="", flush=True)
    while time.perf_counter() < deadline:
        task = latest_task_execution(collector_type, cron_fired_at)
        if task:
            print(f" found task {task['id']}")
            break
        time.sleep(POLL_INTERVAL)
        print(".", end="", flush=True)
    else:
        raise TimeoutError(f"No TaskExecution for {collector_type} appeared within {POLL_TIMEOUT}s after cron fired")

    # Now wait for it to reach a terminal status
    task_id = task["id"]
    print(f"  Polling task {task_id} until completion...", end="", flush=True)
    while time.perf_counter() < deadline:
        resp = requests.get(f"{BASE_URL}/v1/tasks/{task_id}/", auth=AUTH, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        status = data.get("status")
        if status == "completed":
            print(" done")
            return data
        if status in ("failed", "cancelled"):
            print(f" {status}!")
            raise RuntimeError(f"Task {task_id} ended with status={status}")
        time.sleep(POLL_INTERVAL)
        print(".", end="", flush=True)

    raise TimeoutError(f"Task {task_id} did not complete within {POLL_TIMEOUT}s")


def task_duration_seconds(task: dict) -> float:
    """
    Return the collector's actual execution time.

    Preference order:
    1. result_data.elapsed_seconds — the time spent inside collector.gather()
       (most accurate, set by our instrumentation in utils.py)
    2. created → completed_at wall-clock delta — full task overhead including
       DB write; used as fallback if elapsed_seconds is missing.
    """
    result_data = task.get("result_data") or {}
    if "elapsed_seconds" in result_data:
        return float(result_data["elapsed_seconds"])
    created_at = dt.datetime.fromisoformat(task["created"].replace("Z", "+00:00"))
    completed_at = dt.datetime.fromisoformat(task["completed_at"].replace("Z", "+00:00"))
    return (completed_at - created_at).total_seconds()


# ---------------------------------------------------------------------------
# Prometheus helpers
# ---------------------------------------------------------------------------

def read_prometheus_metrics(url: str) -> dict:
    if not url:
        return {}
    try:
        resp = requests.get(url, timeout=5)
        resp.raise_for_status()
    except Exception:
        return {}
    result = {}
    for line in resp.text.splitlines():
        if line.startswith("#") or not line.strip():
            continue
        parts = line.split()
        if len(parts) >= 2:
            result[parts[0]] = float(parts[-1])
    return result


# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------

def save_results(results: dict) -> str:
    os.makedirs(RESULTS_DIR, exist_ok=True)
    date_str = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d_%H%M%S")
    label = f"_{DATA_SCALE}" if DATA_SCALE else ""
    filename = f"cron_{date_str}{label}.json"
    path = os.path.join(RESULTS_DIR, filename)
    with open(path, "w") as f:
        json.dump(results, f, indent=2)
    return path


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def verify_connectivity():
    resp = requests.get(f"{BASE_URL}/v1/", auth=AUTH, timeout=10)
    if not resp.ok:
        print(f"  ERROR: {BASE_URL}/v1/ returned {resp.status_code}")
        raise SystemExit(1)
    print("  OK")


def countdown_to(target: dt.datetime):
    """Print a live countdown until target time is reached."""
    while True:
        remaining = (target - dt.datetime.now(dt.timezone.utc)).total_seconds()
        if remaining <= 0:
            print("\r  Cron window reached!                          ")
            return
        mins, secs = divmod(int(remaining), 60)
        print(f"\r  Time until cron fires: {mins:02d}:{secs:02d}  ", end="", flush=True)
        time.sleep(1)


def observe_one_run(run_number: int, total_runs: int) -> dict:
    """Wait for and capture one cron-triggered collector run."""
    print(f"\n{'=' * 70}")
    print(f"Cron Run {run_number}/{total_runs}")
    print("=" * 70)

    next_cron = next_cron_time(CRON_MINUTE)
    since, until = collection_window_for_cron(next_cron)
    collector = CRON_SCHEDULE.get(CRON_MINUTE, "job_host_summary_service")

    print(f"\n  Next cron fires at : {fmt(next_cron)}")
    print(f"  Collector          : {collector}  (cron minute :{CRON_MINUTE:02d})")
    print(f"  Collection window  : {fmt(since)}  →  {fmt(until)}")
    print()
    print("  *** DATA GENERATION WINDOW ***")
    print("  Run testathon now so that AWX jobs FINISH between:")
    print(f"    {fmt(since)}  and  {fmt(until)}")
    print(f"  You have until {fmt(next_cron)} before the cron fires.")
    print()

    metrics_before = read_prometheus_metrics(METRICS_URL)

    # Wait for the cron to fire (with live countdown)
    countdown_to(next_cron)

    # Add a small buffer so the cron task is actually enqueued
    time.sleep(3)
    cron_fired_at = next_cron - timedelta(seconds=5)  # slight slack for clock drift

    task = wait_for_cron_task(collector, cron_fired_at)
    duration = task_duration_seconds(task)
    result_data = task.get("result_data") or {}
    records_processed = result_data.get("records_processed", "n/a")
    elapsed_seconds = result_data.get("elapsed_seconds", "n/a")

    metrics_after = read_prometheus_metrics(METRICS_URL)

    print(f"\n  Collector         : {collector}")
    print(f"  Task ID           : {task['id']}")
    print(f"  Status            : {task['status']}")
    print(f"  Records processed : {records_processed}")
    print(f"  Gather time       : {elapsed_seconds}s  (inside collector.gather())")
    print(f"  Total task time   : {duration:.3f}s  (created → completed_at)")
    print(f"  Window collected  : {fmt(since)}  →  {fmt(until)}")

    run_result = {
        "run_number": run_number,
        "cron_fired_at": fmt(next_cron),
        "collector_type": collector,
        "collection_window": {"since": fmt(since), "until": fmt(until)},
        "task_id": task["id"],
        "status": task["status"],
        "records_processed": records_processed,
        "gather_seconds": elapsed_seconds,
        "total_task_seconds": round(duration, 3),
        "created": task.get("created"),
        "completed_at": task.get("completed_at"),
    }

    if metrics_before and metrics_after:
        exec_time_key = f'collector_execution_time_seconds_sum{{collector_type="{collector}"}}'
        runs_key = f'collector_runs_total{{collector_type="{collector}"}}'
        run_result["prometheus"] = {
            "execution_time_delta": round(
                metrics_after.get(exec_time_key, 0) - metrics_before.get(exec_time_key, 0), 3
            ),
            "runs_delta": int(
                metrics_after.get(runs_key, 0) - metrics_before.get(runs_key, 0)
            ),
        }

    return run_result


def main():
    print("=" * 70)
    print("Metrics Service — Cron-Based Performance Observer")
    print("=" * 70)
    print(f"  Target      : {BASE_URL}")
    print(f"  User        : {USERNAME}")
    print(f"  Cron minute : :{CRON_MINUTE:02d} (fires at XX:{CRON_MINUTE:02d} each hour)")
    print(f"  Collector   : {CRON_SCHEDULE.get(CRON_MINUTE, 'job_host_summary_service')}")
    print(f"  Observe runs: {OBSERVE_RUNS}")
    print(f"  Data scale  : {DATA_SCALE or '(not set — export DATA_SCALE=<description)'}")
    print(f"  Prometheus  : {METRICS_URL or '(not configured — set METRICS_URL)'}")
    print(f"  Results dir : {RESULTS_DIR}")

    print("\nVerifying connectivity...")
    verify_connectivity()

    run_timestamp = dt.datetime.now(dt.timezone.utc).isoformat()
    all_runs = []

    for i in range(1, OBSERVE_RUNS + 1):
        run_result = observe_one_run(i, OBSERVE_RUNS)
        all_runs.append(run_result)

    # Summary
    durations = [r["total_task_seconds"] for r in all_runs]
    print(f"\n{'=' * 70}")
    print("Summary")
    print("=" * 70)
    for r in all_runs:
        print(f"  Run {r['run_number']:>2}  {r['collection_window']['since']}  "
              f"gather={r['gather_seconds']}s  total={r['total_task_seconds']:.3f}s  "
              f"records={r['records_processed']}  [{r['status']}]")

    if len(durations) > 1:
        avg = sum(durations) / len(durations)
        print(f"\n  Average duration : {avg:.3f}s across {len(durations)} runs")

    results = {
        "script": "benchmark_cron_observer.py",
        "run_timestamp": run_timestamp,
        "data_scale": DATA_SCALE or None,
        "target": BASE_URL,
        "cron_minute": CRON_MINUTE,
        "observe_runs": OBSERVE_RUNS,
        "runs": all_runs,
        "summary": {
            "min_seconds": round(min(durations), 3),
            "max_seconds": round(max(durations), 3),
            "avg_seconds": round(sum(durations) / len(durations), 3),
        },
    }

    path = save_results(results)
    print(f"\n  Results saved → {path}")
    print()


if __name__ == "__main__":
    main()
