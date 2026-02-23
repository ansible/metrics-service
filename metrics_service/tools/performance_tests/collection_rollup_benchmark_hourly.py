#!/usr/bin/env python
"""
Performance test for metrics-service collection and rollup.

Runs the snapshot collector (main_host) once, then runs the two time-scoped collectors
(job_host_summary, main_jobevent) once per hour for 24 hours, then triggers the daily
rollup.

"""

# ruff: noqa: T201, E402
import contextlib
import os
import sys
import threading
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


class PeakMemoryMonitor:
    """Measures peak RSS memory during task execution by polling in a background thread."""

    def __init__(self, process, interval=0.05):
        self._process = process
        self._interval = interval
        self._peak = 0.0
        self._stop = threading.Event()

    def __enter__(self):
        self._peak = get_memory_mb(self._process)
        self._stop.clear()
        self._thread = threading.Thread(target=self._poll, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *args):
        self._stop.set()
        self._thread.join()

    def _poll(self):
        while not self._stop.is_set():
            self._peak = max(self._peak, get_memory_mb(self._process))
            time.sleep(self._interval)

    @property
    def peak_mb(self):
        return self._peak


def run_snapshot_phase(test_date, process, peak_memory_mb):
    """Phase 1: Run snapshot collector (main_host) once."""
    print("Phase 1: Snapshot collector (main_host) — run once")
    snapshot_start = time.time()
    try:
        with PeakMemoryMonitor(process) as monitor:
            collect_main_host_hourly(hour_timestamp=test_date.isoformat(), database="awx")
    except Exception as e:
        print(f"  Error: {e}")
    snapshot_duration = time.time() - snapshot_start
    peak_memory_mb = max(peak_memory_mb, monitor.peak_mb)
    print(f"  Duration: {snapshot_duration:.2f}s")
    print(f"  Memory: {get_memory_mb(process):.1f} MB\n")
    return snapshot_duration, peak_memory_mb


def run_hourly_phase(test_date, process, peak_memory_mb, baseline_memory_mb):
    """Phase 2: Run hourly collectors for each hour in a 24-hour period."""
    from django.db.models import Count, Sum

    hourly_collectors = [
        ("job_host_summary", collect_job_host_summary_hourly),
        ("main_jobevent", collect_host_metrics_hourly),
    ]

    collector_totals = {name: 0.0 for name, _ in hourly_collectors}
    collector_peak_memory = {name: baseline_memory_mb for name, _ in hourly_collectors}
    hour_timings, failed_hours = [], []

    print("Phase 2: Hourly collectors — 24 hours")
    print(f"  {'Hour':<6} {'job_host_summary':>18} {'main_jobevent':>15} {'Total':>10} {'Memory MB':>11}")

    hourly_collection_start = time.time()

    for hour in range(24):
        hour_timestamp = (test_date + timedelta(hours=hour)).isoformat()
        hour_start = time.time()
        hour_collector_times = {}
        hour_had_error = False

        for collector_name, collector_func in hourly_collectors:
            collector_start = time.time()
            try:
                with PeakMemoryMonitor(process) as monitor:
                    collector_func(hour_timestamp=hour_timestamp, database="awx")
            except Exception as e:
                hour_had_error = True
                failed_hours.append(f"{collector_name}:hour_{hour}")
                print(f"  Error at hour {hour}, {collector_name}: {e}")
            collector_duration = time.time() - collector_start
            hour_collector_times[collector_name] = collector_duration
            collector_totals[collector_name] += collector_duration
            collector_peak_memory[collector_name] = max(collector_peak_memory[collector_name], monitor.peak_mb)
            peak_memory_mb = max(peak_memory_mb, monitor.peak_mb)
        hour_total = time.time() - hour_start
        current_memory = get_memory_mb(process)
        hour_timings.append(hour_total)

        jhs_time = hour_collector_times.get("job_host_summary", 0)
        mje_time = hour_collector_times.get("main_jobevent", 0)
        err_flag = " *" if hour_had_error else ""
        print(
            f"  {hour:>4}   {jhs_time:>17.2f}s {mje_time:>14.2f}s {hour_total:>9.2f}s {current_memory:>10.1f}{err_flag}"
        )

    hourly_collection_duration = time.time() - hourly_collection_start

    stats = HourlyMetricsCollection.objects.aggregate(total_size=Sum("data_size_bytes"), count=Count("id"))
    total_size = stats["total_size"] or 0
    collections_count = stats["count"]

    print()
    print("  Hourly Collection Summary:")
    print(f"    Total duration: {hourly_collection_duration:.1f}s ({hourly_collection_duration / 60:.1f} min)")
    print(f"    Collections created: {collections_count}")
    print(f"    Total data size: {total_size / 1024 / 1024:.2f} MB")
    for name, total in collector_totals.items():
        print(f"    {name} total: {total:.1f}s")
    if hour_timings:
        print(f"    Slowest hour: {max(hour_timings):.2f}s (hour {hour_timings.index(max(hour_timings))})")
        print(f"    Fastest hour: {min(hour_timings):.2f}s (hour {hour_timings.index(min(hour_timings))})")
    if failed_hours:
        print(f"    Failed collections: {len(failed_hours)} (* in table above)")
        for failure in failed_hours:
            print(f"      - {failure}")
    print()

    return hourly_collection_duration, peak_memory_mb, collector_totals, collector_peak_memory


def run_rollup_phase(test_date, process, peak_memory_mb):
    """Phase 3: Run daily rollup."""
    print("Phase 3: Daily rollup")

    rollup_start = time.time()
    rollup_duration = 0.0

    try:
        with PeakMemoryMonitor(process) as monitor:
            result = daily_metrics_rollup(summary_date=test_date.date().isoformat())
        rollup_duration = time.time() - rollup_start
        peak_memory_mb = max(peak_memory_mb, monitor.peak_mb)

        summaries = DailyMetricsSummary.objects.filter(summary_date=test_date.date())

        print(f"  Duration: {rollup_duration:.2f}s")
        print(f"  Status: {result.get('status')}")
        print(f"  Summaries created: {summaries.count()}")
        print(f"  Memory after rollup: {get_memory_mb(process):.1f} MB")
        print()

    except Exception as e:
        rollup_duration = time.time() - rollup_start
        print(f"  Rollup failed after {rollup_duration:.2f}s: {e}")
        peak_memory_mb = max(peak_memory_mb, monitor.peak_mb)
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
    print(f"  Peak memory:     {peak_memory_mb:.1f} MB (RSS, sampled every 50ms during execution)")
    print(f"  Delta:           {peak_memory_mb - baseline_memory_mb:.1f} MB")
    print()

    # Output table sizes
    from django.core import serializers
    from django.db.models import Count

    hourly_count = HourlyMetricsCollection.objects.aggregate(count=Count("id"))["count"]
    daily_count = DailyMetricsSummary.objects.aggregate(count=Count("id"))["count"]

    hourly_json = serializers.serialize("json", HourlyMetricsCollection.objects.all())
    daily_json = serializers.serialize("json", DailyMetricsSummary.objects.all())

    hourly_size_mb = len(hourly_json.encode()) / 1024 / 1024
    daily_size_mb = len(daily_json.encode()) / 1024 / 1024

    print("  Output Table Sizes:")
    print(f"    HourlyMetricsCollection: {hourly_count} rows, {hourly_size_mb:.2f} MB")
    print(f"    DailyMetricsSummary:     {daily_count} rows, {daily_size_mb:.2f} MB")
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

    print("Warm-up: running throwaway collector call to initialize DB connections and caches...")
    with contextlib.suppress(Exception):
        collect_main_host_hourly(hour_timestamp=test_date.isoformat(), database="awx")
    HourlyMetricsCollection.objects.all().delete()
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
