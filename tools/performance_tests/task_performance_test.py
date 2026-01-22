#!/usr/bin/env python
"""
Test individual task performance with timing and memory measurements.

Tests each relevant collection and rollup task separately:
- Hourly collection tasks (3 collectors)
- Daily rollup pipeline (5 steps)
- 12-hour anonymized collection

Usage:
    python tools/performance_tests/task_performance_test.py --task all
    python tools/performance_tests/task_performance_test.py --task hourly
    python tools/performance_tests/task_performance_test.py --task daily
    python tools/performance_tests/task_performance_test.py --task collect_job_host_summary_hourly
"""

import argparse
import os
import sys
from collections.abc import Callable
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# Setup Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "metrics_service.settings")
import django  # noqa: E402

django.setup()

from perf_utils import (  # noqa: E402
    PerformanceMetrics,
    PerformanceReport,
    PerformanceTimer,
    get_output_dir,
    logger,
)
from task_definitions import (  # noqa: E402
    ALL_TASKS,
    DAILY_ROLLUP_TASKS,
    HOURLY_TASKS,
)

from apps.tasks.models import HourlyMetricsCollection  # noqa: E402
from apps.tasks.tasks_collector import full_process_anonymize  # noqa: E402


def run_task_with_measurement(task_name: str, task_func: Callable, log_file: Path) -> PerformanceMetrics:
    """
    Run a single task with performance measurement.

    Args:
        task_name: Name of the task
        task_func: Task function to execute
        log_file: File to write timing logs

    Returns:
        PerformanceMetrics object with results
    """
    logger.info(f"\n{'=' * 80}")
    logger.info(f"Testing task: {task_name}")
    logger.info(f"{'=' * 80}")

    with PerformanceTimer(task_name, log_file=log_file) as timer:
        try:
            # Execute the task
            result = task_func()
            logger.info(f"Task result: {result}")
        except Exception as e:
            logger.error(f"Task failed with error: {e}", exc_info=True)
            raise

    return timer.metrics


def run_hourly_tasks(log_file: Path) -> list[PerformanceMetrics]:
    """
    Run all hourly collection tasks sequentially.

    Args:
        log_file: File to write timing logs

    Returns:
        List of performance metrics for each task
    """
    logger.info("\n" + "=" * 80)
    logger.info("TESTING HOURLY COLLECTION TASKS")
    logger.info("=" * 80)

    results = []

    # Check existing data
    existing_count = HourlyMetricsCollection.objects.count()
    logger.info(f"Existing hourly collections: {existing_count}")

    for task_name, task_func in HOURLY_TASKS.items():
        metrics = run_task_with_measurement(task_name, task_func, log_file)
        results.append(metrics)

    # Show new data created
    new_count = HourlyMetricsCollection.objects.count()
    logger.info(f"Hourly collections after tests: {new_count} (+{new_count - existing_count})")

    return results


def run_daily_rollup_tasks(log_file: Path) -> list[PerformanceMetrics]:
    """
    Run daily rollup pipeline tasks sequentially.

    Args:
        log_file: File to write timing logs

    Returns:
        List of performance metrics for each task
    """
    logger.info("\n" + "=" * 80)
    logger.info("TESTING DAILY ROLLUP PIPELINE")
    logger.info("=" * 80)

    results = []

    # Check that we have hourly data to aggregate
    hourly_count = HourlyMetricsCollection.objects.filter(status="collected").count()
    logger.info(f"Available hourly collections for rollup: {hourly_count}")

    if hourly_count == 0:
        logger.warning("No hourly collections available! Run hourly tasks first or generate test data.")
        return results

    for task_name, task_func in DAILY_ROLLUP_TASKS.items():
        try:
            metrics = run_task_with_measurement(task_name, task_func, log_file)
            results.append(metrics)
        except Exception as e:
            logger.error(f"Task {task_name} failed, stopping pipeline: {e}")
            break

    return results


def run_anonymized_task(log_file: Path) -> list[PerformanceMetrics]:
    """
    Run 12-hour anonymized collection task.

    Args:
        log_file: File to write timing logs

    Returns:
        List with single performance metric
    """
    logger.info("\n" + "=" * 80)
    logger.info("TESTING 12-HOUR ANONYMIZED COLLECTION")
    logger.info("=" * 80)

    try:
        metrics = run_task_with_measurement("full_process_anonymize", full_process_anonymize, log_file)
        return [metrics]
    except Exception as e:
        logger.error(f"Anonymized task failed: {e}")
        return []


def run_all_tasks(log_file: Path) -> list[PerformanceMetrics]:
    """
    Run all tasks in sequence.

    Args:
        log_file: File to write timing logs

    Returns:
        Combined list of all performance metrics
    """
    all_results = []

    # Run hourly tasks first
    all_results.extend(run_hourly_tasks(log_file))

    # Run daily rollup pipeline
    all_results.extend(run_daily_rollup_tasks(log_file))

    # Run anonymized collection
    all_results.extend(run_anonymized_task(log_file))

    return all_results


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Test individual task performance with timing and memory measurements")
    parser.add_argument(
        "--task",
        choices=list(ALL_TASKS.keys()) + ["all", "hourly", "daily", "anonymized"],
        required=True,
        help="Task or task group to test",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Output directory for results (default: auto-generated with timestamp)",
    )

    args = parser.parse_args()

    # Create output directory
    if args.output_dir:
        output_dir = args.output_dir
        output_dir.mkdir(parents=True, exist_ok=True)
    else:
        output_dir = get_output_dir("task_perf")

    log_file = output_dir / "task_timing.log"
    logger.info(f"Results will be written to: {output_dir}")
    logger.info(f"Timing log file: {log_file}")

    # Run tests based on selection
    results = []

    if args.task == "all":
        results = run_all_tasks(log_file)
    elif args.task == "hourly":
        results = run_hourly_tasks(log_file)
    elif args.task == "daily":
        results = run_daily_rollup_tasks(log_file)
    elif args.task == "anonymized":
        results = run_anonymized_task(log_file)
    else:
        # Single task
        task_func = ALL_TASKS[args.task]
        metrics = run_task_with_measurement(args.task, task_func, log_file)
        results = [metrics]

    # Generate reports
    if results:
        logger.info("\n" + "=" * 80)
        logger.info("GENERATING REPORTS")
        logger.info("=" * 80)

        report = PerformanceReport(results)
        report.generate_markdown(output_dir / "report.md")
        report.generate_json(output_dir / "report.json")

        logger.info(f"\nTest complete! Results saved to {output_dir}")
    else:
        logger.warning("No results to report")


if __name__ == "__main__":
    main()
