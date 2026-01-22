#!/usr/bin/env python
"""
Force all collection tasks to run simultaneously and measure performance.

This script simulates running the complete metrics service with all tasks
executing together, measuring overall system performance under load.

Usage:
    python tools/performance_tests/run_all_tasks.py
    python tools/performance_tests/run_all_tasks.py --output-dir ./results
"""

import argparse
import concurrent.futures
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
from task_definitions import ALL_TASKS, TASKS_IN_ORDER  # noqa: E402

from apps.tasks.models import HourlyMetricsCollection  # noqa: E402


def create_overall_metrics(
    task_name: str, timer: PerformanceTimer, results: list[PerformanceMetrics], total_tasks: int
) -> PerformanceMetrics:
    """Create summary metrics for overall test run."""
    return PerformanceMetrics(
        task_name=task_name,
        start_time=timer.metrics.start_time,
        end_time=timer.metrics.end_time,
        duration_seconds=timer.metrics.duration_seconds,
        duration_ms=timer.metrics.duration_ms,
        memory_before_mb=timer.metrics.memory_before_mb,
        memory_after_mb=timer.metrics.memory_after_mb,
        memory_delta_mb=timer.metrics.memory_delta_mb,
        memory_peak_mb=timer.metrics.memory_peak_mb,
        status="success",
        additional_data={
            "total_tasks": total_tasks,
            "successful_tasks": sum(1 for r in results if r.status == "success"),
            "failed_tasks": sum(1 for r in results if r.status == "failed"),
        },
    )


def run_task_wrapper(task_name: str, task_func: Callable, log_file: Path) -> tuple[str, PerformanceMetrics]:
    """
    Wrapper to run a task and return its name and metrics.

    Args:
        task_name: Name of the task
        task_func: Task function to execute
        log_file: File to write timing logs

    Returns:
        Tuple of (task_name, PerformanceMetrics)
    """
    logger.info(f"[PARALLEL] Starting {task_name}")

    with PerformanceTimer(task_name, log_file=log_file) as timer:
        try:
            result = task_func()
            logger.info(f"[PARALLEL] {task_name} completed: {result}")
        except Exception as e:
            logger.error(f"[PARALLEL] {task_name} failed: {e}", exc_info=True)
            raise

    return task_name, timer.metrics


def run_tasks_parallel(tasks: dict[str, Callable], log_file: Path, max_workers: int = 5) -> list[PerformanceMetrics]:
    """
    Run multiple tasks in parallel using ThreadPoolExecutor.

    Args:
        tasks: Dictionary of task_name -> task_function
        log_file: File to write timing logs
        max_workers: Maximum number of parallel workers

    Returns:
        List of PerformanceMetrics for all tasks
    """
    logger.info(f"\nRunning {len(tasks)} tasks in parallel with {max_workers} workers")

    results = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        futures = {
            executor.submit(run_task_wrapper, task_name, task_func, log_file): task_name
            for task_name, task_func in tasks.items()
        }

        # Wait for completion and collect results
        for future in concurrent.futures.as_completed(futures):
            task_name = futures[future]
            try:
                _, metrics = future.result()
                results.append(metrics)
                logger.info(f"[COMPLETE] {task_name}")
            except Exception as e:
                logger.error(f"[FAILED] {task_name}: {e}")

    return results


def run_all_tasks_parallel(log_file: Path) -> list[PerformanceMetrics]:
    """
    Run all collection and rollup tasks in parallel.

    This simulates the service under maximum load with all tasks running together.

    Args:
        log_file: File to write timing logs

    Returns:
        List of performance metrics for all tasks
    """
    logger.info("\n" + "=" * 80)
    logger.info("RUNNING ALL TASKS IN PARALLEL")
    logger.info("=" * 80)

    # Check existing data
    hourly_count = HourlyMetricsCollection.objects.count()
    logger.info(f"Existing hourly collections: {hourly_count}")

    # Run all tasks in parallel
    with PerformanceTimer("all_tasks_parallel", log_file=log_file) as overall_timer:
        results = run_tasks_parallel(ALL_TASKS, log_file, max_workers=8)

    # Add overall timing as a summary metric
    overall_metrics = create_overall_metrics("ALL_TASKS_PARALLEL_TOTAL", overall_timer, results, len(ALL_TASKS))
    results.append(overall_metrics)

    # Show data changes
    new_hourly_count = HourlyMetricsCollection.objects.count()
    logger.info(f"Hourly collections after parallel run: {new_hourly_count} (+{new_hourly_count - hourly_count})")

    return results


def run_all_tasks_sequential(log_file: Path) -> list[PerformanceMetrics]:
    """
    Run all tasks sequentially in the order they would normally execute.

    Args:
        log_file: File to write timing logs

    Returns:
        List of performance metrics for all tasks
    """
    logger.info("\n" + "=" * 80)
    logger.info("RUNNING ALL TASKS SEQUENTIALLY")
    logger.info("=" * 80)

    results = []

    with PerformanceTimer("all_tasks_sequential", log_file=log_file) as overall_timer:
        for task_name, task_func in TASKS_IN_ORDER:
            try:
                _, metrics = run_task_wrapper(task_name, task_func, log_file)
                results.append(metrics)
            except Exception as e:
                logger.error(f"Task {task_name} failed, continuing with remaining tasks: {e}")

    # Add overall timing
    overall_metrics = create_overall_metrics("ALL_TASKS_SEQUENTIAL_TOTAL", overall_timer, results, len(TASKS_IN_ORDER))
    results.append(overall_metrics)

    return results


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Force all tasks to run and measure performance")
    parser.add_argument(
        "--mode",
        choices=["parallel", "sequential", "both"],
        default="parallel",
        help="Execution mode (default: parallel)",
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
        output_dir = get_output_dir("all_tasks")

    log_file = output_dir / "all_tasks_timing.log"
    logger.info(f"Results will be written to: {output_dir}")
    logger.info(f"Timing log file: {log_file}")

    all_results = []

    # Run based on mode
    if args.mode in ["parallel", "both"]:
        results = run_all_tasks_parallel(log_file)
        all_results.extend(results)

    if args.mode in ["sequential", "both"]:
        results = run_all_tasks_sequential(log_file)
        all_results.extend(results)

    # Generate reports
    if all_results:
        logger.info("\n" + "=" * 80)
        logger.info("GENERATING REPORTS")
        logger.info("=" * 80)

        report = PerformanceReport(all_results)
        report.generate_markdown(output_dir / "report.md")
        report.generate_json(output_dir / "report.json")

        logger.info(f"\nTest complete! Results saved to {output_dir}")

        # Print summary
        logger.info("\n" + "=" * 80)
        logger.info("SUMMARY")
        logger.info("=" * 80)
        for result in all_results:
            if "TOTAL" in result.task_name:
                logger.info(
                    f"{result.task_name}:\n"
                    f"  Duration: {result.duration_seconds:.2f}s ({result.duration_ms:.2f}ms)\n"
                    f"  Memory: {result.memory_delta_mb:+.2f}MB\n"
                    f"  Tasks: {result.additional_data.get('successful_tasks', 0)}/{result.additional_data.get('total_tasks', 0)} successful"
                )
    else:
        logger.warning("No results to report")


if __name__ == "__main__":
    main()
