#!/usr/bin/env python
"""
Performance test for metrics-service collection and rollup.

Runs the snapshot collector (main_host) once, then runs the two time-scoped collectors
(job_host_summary, main_jobevent) once per hour for 24 hours, then triggers the daily
rollup.

The daily benchmark (collection_rollup_benchmark_daily.py) can be used to benchmark
the snapshot collector in isolation.
"""

# ruff: noqa: T201, E402
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import psutil

# Setup Django
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "metrics_service.settings")

import django

django.setup()

from apps.tasks.models import DailyMetricsSummary, HourlyMetricsCollection
from apps.tasks.tasks_collector import (
    collect_host_metrics_hourly,
    collect_job_host_summary_hourly,
    collect_main_host_hourly,
    daily_metrics_rollup,
)


def get_memory_mb(process):
    """Return current RSS in MB."""
    return process.memory_info().rss / 1024 / 1024


def update_peak(process, peak_memory_mb):
    """Update and return the peak memory high-water mark."""
    current = get_memory_mb(process)
    return max(current, peak_memory_mb)


def run_snapshot_phase(test_date, process, peak_memory_mb):
    """Phase 1: Run snapshot collector (main_host) once."""
    print("Phase 1: Snapshot collector (main_host) — run once")
    snapshot_start = time.time()
    try:
        collect_main_host_hourly(hour_timestamp=test_date.isoformat(), database="awx")
    except Exception as e:
        print(f"  Error: {e}")
    snapshot_duration = time.time() - snapshot_start
    peak_memory_mb = update_peak(process, peak_memory_mb)
    print(f"  Duration: {snapshot_duration:.2f}s")
    print(f"  Memory: {get_memory_mb(process):.1f} MB\n")
    return snapshot_duration, peak_memory_mb


def run_hourly_phase(test_date, process, peak_memory_mb, baseline_memory_mb):
    """Phase 2: Run hourly collectors for each hour in a 24-hour period."""
    hourly_collectors = [
        ("job_host_summary", collect_job_host_summary_hourly),
        ("main_jobevent", collect_host_metrics_hourly),
    ]

    collector_totals = {name: 0.0 for name, _ in hourly_collectors}
    collector_peak_memory = {name: baseline_memory_mb for name, _ in hourly_collectors}
    hour_timings = []

    print("Phase 2: Hourly collectors — 24 hours")
    print(f"  {'Hour':<6} {'job_host_summary':>18} {'main_jobevent':>15} {'Total':>10} {'Memory MB':>11}")

    hourly_collection_start = time.time()

    for hour in range(24):
        hour_timestamp = (test_date + timedelta(hours=hour)).isoformat()
        hour_start = time.time()
        hour_collector_times = {}

        for collector_name, collector_func in hourly_collectors:
            collector_start = time.time()
            try:
                collector_func(hour_timestamp=hour_timestamp, database="awx")
            except Exception as e:
                print(f"  Error at hour {hour}, {collector_name}: {e}")
            collector_duration = time.time() - collector_start
            hour_collector_times[collector_name] = collector_duration
            collector_totals[collector_name] += collector_duration
            collector_memory = get_memory_mb(process)
            collector_peak_memory[collector_name] = max(collector_peak_memory[collector_name], collector_memory)

        peak_memory_mb = update_peak(process, peak_memory_mb)
        hour_total = time.time() - hour_start
        current_memory = get_memory_mb(process)
        hour_timings.append(hour_total)

        jhs_time = hour_collector_times.get("job_host_summary", 0)
        mje_time = hour_collector_times.get("main_jobevent", 0)
        print(f"  {hour:>4}   {jhs_time:>17.2f}s {mje_time:>14.2f}s {hour_total:>9.2f}s {current_memory:>10.1f}")

    hourly_collection_duration = time.time() - hourly_collection_start

    collections = HourlyMetricsCollection.objects.all()
    total_size = sum(c.data_size_bytes for c in collections)

    print()
    print("  Hourly Collection Summary:")
    print(f"    Total duration: {hourly_collection_duration:.1f}s ({hourly_collection_duration / 60:.1f} min)")
    print(f"    Collections created: {collections.count()}")
    print(f"    Total data size: {total_size / 1024 / 1024:.2f} MB")
    for name, total in collector_totals.items():
        print(f"    {name} total: {total:.1f}s")
    if hour_timings:
        print(f"    Slowest hour: {max(hour_timings):.2f}s (hour {hour_timings.index(max(hour_timings))})")
        print(f"    Fastest hour: {min(hour_timings):.2f}s (hour {hour_timings.index(min(hour_timings))})")
    print()

    return hourly_collection_duration, peak_memory_mb, collector_totals, collector_peak_memory


def run_rollup_phase(test_date, process, peak_memory_mb):
    """Phase 3: Run daily rollup."""
    print("Phase 3: Daily rollup")

    rollup_start = time.time()
    rollup_duration = 0.0

    try:
        result = daily_metrics_rollup(summary_date=test_date.date().isoformat())
        rollup_duration = time.time() - rollup_start
        peak_memory_mb = update_peak(process, peak_memory_mb)

        summaries = DailyMetricsSummary.objects.filter(summary_date=test_date.date())

        print(f"  Duration: {rollup_duration:.2f}s")
        print(f"  Status: {result.get('status')}")
        print(f"  Summaries created: {summaries.count()}")
        print(f"  Memory after rollup: {get_memory_mb(process):.1f} MB")
        print()

    except Exception as e:
        print(f"  Rollup failed: {e}")
        peak_memory_mb = update_peak(process, peak_memory_mb)
        print()

    return rollup_duration, peak_memory_mb


def print_final_summary(
    snapshot_duration,
    hourly_collection_duration,
    rollup_duration,
    collector_totals,
    collector_peak_memory,
    baseline_memory_mb,
    peak_memory_mb,
    process,
):
    """Print the final benchmark results."""
    total_duration = snapshot_duration + hourly_collection_duration + rollup_duration

    print(f"{'=' * 80}")
    print("  Final Results")
    print(f"{'=' * 80}\n")
    print(f"  Snapshot (main_host):  {snapshot_duration:.2f}s")
    print(f"  Hourly collection:    {hourly_collection_duration:.1f}s ({hourly_collection_duration / 60:.1f} min)")
    for name, total in collector_totals.items():
        print(f"    {name}: {total:.1f}s total, peak {collector_peak_memory[name]:.1f} MB")
    print(f"  Rollup:               {rollup_duration:.2f}s, {get_memory_mb(process):.1f} MB after")
    print(f"  Total:                {total_duration:.1f}s ({total_duration / 60:.1f} min)")
    print()
    print(f"  Baseline memory: {baseline_memory_mb:.1f} MB")
    print(f"  Peak memory:     {peak_memory_mb:.1f} MB")
    print(f"  Delta:           {peak_memory_mb - baseline_memory_mb:.1f} MB")
    print()


def run_collection_rollup_benchmark():
    test_date_str = os.environ.get("TEST_DATE", "2024-01-25")
    test_date = datetime.fromisoformat(test_date_str).replace(hour=0, minute=0, second=0, microsecond=0)

    print(f"\n{'=' * 80}")
    print("  Metrics Collection & Rollup Performance Test")
    print(f"  Test Date: {test_date.date()}")
    print(f"{'=' * 80}\n")

    print("Cleaning old collections...")
    HourlyMetricsCollection.objects.all().delete()
    DailyMetricsSummary.objects.all().delete()
    print("Done\n")

    process = psutil.Process()
    baseline_memory_mb = get_memory_mb(process)
    peak_memory_mb = baseline_memory_mb

    snapshot_duration, peak_memory_mb = run_snapshot_phase(test_date, process, peak_memory_mb)

    hourly_collection_duration, peak_memory_mb, collector_totals, collector_peak_memory = run_hourly_phase(
        test_date,
        process,
        peak_memory_mb,
        baseline_memory_mb,
    )

    rollup_duration, peak_memory_mb = run_rollup_phase(test_date, process, peak_memory_mb)

    print_final_summary(
        snapshot_duration,
        hourly_collection_duration,
        rollup_duration,
        collector_totals,
        collector_peak_memory,
        baseline_memory_mb,
        peak_memory_mb,
        process,
    )


if __name__ == "__main__":
    run_collection_rollup_benchmark()
