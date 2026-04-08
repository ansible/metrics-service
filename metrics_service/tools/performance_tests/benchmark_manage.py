# ruff: noqa: T201
import time

from apps.tasks.collectors import collect_hourly_metrics, collect_snapshot_metrics, daily_metrics_rollup

TEST_DATE = "2024-01-25"

SNAPSHOT_COLLECTORS = [
    "execution_environments",
    "config",
    "controller_version_service",
    "table_metadata",
]

HOURLY_COLLECTORS = [
    "job_host_summary_service",
    "unified_jobs",
    "credentials_service",
    "main_jobevent_service",
]

print("=" * 70)
print("Metrics Service Pipeline Benchmark (manage.py)")
print("=" * 70)
print(f"  Test date : {TEST_DATE}")

# Phase 1 — Snapshot collectors
print("\n" + "=" * 70)
print("Phase 1: Snapshot collectors (run once each)")
print("=" * 70)
print(f"  {'Collector':<35} {'Duration':>10}")
print(f"  {'---------':<35} {'--------':>10}")

snapshot_start = time.perf_counter()
for collector in SNAPSHOT_COLLECTORS:
    start = time.perf_counter()
    collect_snapshot_metrics(collector_type=collector)
    elapsed = time.perf_counter() - start
    print(f"  {collector:<35} {elapsed:>8.2f}s")

snapshot_elapsed = time.perf_counter() - snapshot_start
print(f"\n  Total: {snapshot_elapsed:.1f}s")

# Phase 2 — Hourly collection
print("\n" + "=" * 70)
print("Phase 2: Hourly collectors (24 hours x 4 collectors)")
print("=" * 70)
print(f"  {'Hour':<6} {'Collector':<35} {'Duration':>10}")
print(f"  {'----':<6} {'---------':<35} {'--------':>10}")

hourly_start = time.perf_counter()
for hour in range(24):
    hour_ts = f"{TEST_DATE}T{hour:02d}:00:00Z"
    for collector in HOURLY_COLLECTORS:
        start = time.perf_counter()
        collect_hourly_metrics(collector_type=collector, hour_timestamp=hour_ts)
        elapsed = time.perf_counter() - start
        print(f"  {hour:<6} {collector:<35} {elapsed:>8.2f}s")

hourly_elapsed = time.perf_counter() - hourly_start
print(f"\n  Total: {hourly_elapsed:.1f}s ({hourly_elapsed / 60:.1f} min)")

# Phase 3 — Daily rollup
print("\n" + "=" * 70)
print("Phase 3: Daily rollup")
print("=" * 70)
start = time.perf_counter()
daily_metrics_rollup(summary_date=TEST_DATE)
rollup_elapsed = time.perf_counter() - start
print(f"  Duration: {rollup_elapsed:.2f}s")

total_elapsed = snapshot_elapsed + hourly_elapsed + rollup_elapsed

# Summary
print("\n" + "=" * 70)
print("Summary")
print("=" * 70)
print(f"  Snapshot collectors: {snapshot_elapsed:>8.2f}s")
print(f"  Hourly collection  : {hourly_elapsed:>8.1f}s ({hourly_elapsed / 60:.1f} min)")
print(f"  Daily rollup       : {rollup_elapsed:>8.2f}s")
print(f"  Total              : {total_elapsed:>8.1f}s ({total_elapsed / 60:.1f} min)")
print()
