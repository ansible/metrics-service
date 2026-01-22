"""
Shared task definitions for performance testing.

This module provides a single source of truth for all tasks being tested,
avoiding duplication across test scripts.
"""

from apps.tasks.tasks_collector import (
    collect_host_metrics_hourly,
    collect_job_host_summary_hourly,
    collect_main_host_hourly,
    daily_anonymize_and_prepare,
    daily_metrics_rollup,
    full_process_anonymize,
    send_anonymized_to_segment,
)
from apps.tasks.tasks_system import cleanup_metrics_data

# Task groups organized by execution pattern
HOURLY_TASKS = {
    "collect_job_host_summary_hourly": collect_job_host_summary_hourly,
    "collect_host_metrics_hourly": collect_host_metrics_hourly,
    "collect_main_host_hourly": collect_main_host_hourly,
}

DAILY_ROLLUP_TASKS = {
    "daily_metrics_rollup": daily_metrics_rollup,
    "daily_anonymize_and_prepare": daily_anonymize_and_prepare,
    "send_anonymized_to_segment": send_anonymized_to_segment,
    "cleanup_metrics_data": cleanup_metrics_data,
}

ANONYMIZED_TASKS = {
    "full_process_anonymize": full_process_anonymize,
}

# All tasks combined
ALL_TASKS = {**HOURLY_TASKS, **DAILY_ROLLUP_TASKS, **ANONYMIZED_TASKS}

# Tasks in normal execution order (for sequential testing)
TASKS_IN_ORDER = [
    # Step 1: Hourly collections (staggered but we'll run them sequentially)
    ("collect_job_host_summary_hourly", collect_job_host_summary_hourly),
    ("collect_host_metrics_hourly", collect_host_metrics_hourly),
    ("collect_main_host_hourly", collect_main_host_hourly),
    # Step 2: Daily rollup pipeline
    ("daily_metrics_rollup", daily_metrics_rollup),
    ("daily_anonymize_and_prepare", daily_anonymize_and_prepare),
    ("send_anonymized_to_segment", send_anonymized_to_segment),
    # Step 3: Anonymized collection
    ("full_process_anonymize", full_process_anonymize),
    # Step 4: Cleanup
    ("cleanup_metrics_data", cleanup_metrics_data),
]
