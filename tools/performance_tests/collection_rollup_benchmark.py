#!/usr/bin/env python
"""
Simple performance test for metrics-service collection and rollup.

Takes time measurement in seconds to:
1. Collect metrics for one day (24 hours). Should be 3 collectors × 24 hours = 72 collections
2. Roll up those collections into daily summaries

Usage:
    TEST_DATE=2024-01-16 python simple_test.py
    (Defaults to 2024-01-16 if not specified)
"""
# ruff: noqa: T201, E402
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

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


def main():
    # Get test date from environment or use default
    test_date_str = os.environ.get("TEST_DATE", "2024-01-16")
    test_date = datetime.fromisoformat(test_date_str).replace(hour=0, minute=0, second=0, microsecond=0)

    print(f"\n{'=' * 80}")
    print("  Metrics Performance Test")
    print(f"  Test Date: {test_date.date()}")
    print(f"{'=' * 80}\n")

    # Clean up any existing collections
    print("Cleaning old collections...")
    HourlyMetricsCollection.objects.all().delete()
    DailyMetricsSummary.objects.all().delete()
    print("✓ Cleaned\n")

    # -------------------------------------------------------------------------
    # STEP 1: Run Collection (24 hours)
    # -------------------------------------------------------------------------
    print("Running collection")
    print()

    collectors = [
        ("job_host_summary", collect_job_host_summary_hourly),
        ("main_host", collect_host_metrics_hourly),
        ("main_jobevent", collect_main_host_hourly),
    ]

    collection_start = time.time()

    # Run collectors for each hour of the day
    for hour in range(24):
        hour_timestamp = (test_date + timedelta(hours=hour)).isoformat()

        for collector_name, collector_func in collectors:
            try:
                collector_func(hour_timestamp=hour_timestamp, database="awx")
            except Exception as e:
                print(f"  Error at hour {hour}, collector {collector_name}: {e}")

    collection_duration = time.time() - collection_start

    # Check what was collected
    collections = HourlyMetricsCollection.objects.all()
    total_size = sum(c.data_size_bytes for c in collections)

    print()
    print("Collection Results:")
    print(f"  Duration: {collection_duration:.1f}s ({collection_duration / 60:.1f} min)")
    print(f"  Collections created: {collections.count()}")
    print(f"  Total size: {total_size / 1024 / 1024:.2f} MB")
    print()

    # -------------------------------------------------------------------------
    # STEP 2: Run Rollup
    # -------------------------------------------------------------------------
    print("Running rollup...")

    rollup_start = time.time()

    try:
        result = daily_metrics_rollup(summary_date=test_date.date().isoformat())
        rollup_duration = time.time() - rollup_start

        summaries = DailyMetricsSummary.objects.filter(summary_date=test_date.date())

        print("Rollup Results:")
        print(f"  Duration: {rollup_duration:.2f}s")
        print(f"  Status: {result.get('status')}")
        print(f"  Summaries created: {summaries.count()}")
        print()

    except Exception as e:
        print(f"  Rollup failed: {e}")
        rollup_duration = 0

    # -------------------------------------------------------------------------
    # FINAL SUMMARY
    # -------------------------------------------------------------------------
    print(f"{'=' * 80}")
    print("  Final Results")
    print(f"{'=' * 80}\n")
    print(f"Collection: {collection_duration:.1f}s ({collection_duration / 60:.1f} min)")
    print(f"Rollup:     {rollup_duration:.2f}s")
    print(
        f"Total:      {collection_duration + rollup_duration:.1f}s ({(collection_duration + rollup_duration) / 60:.1f} min)"
    )
    print()


if __name__ == "__main__":
    main()
