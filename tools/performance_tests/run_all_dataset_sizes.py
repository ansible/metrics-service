#!/usr/bin/env python
"""
Automated performance testing across all dataset sizes.

Runs complete performance test suite across small, medium, and large datasets:
1. Generate test data for each size
2. Run individual task performance tests
3. Run all tasks together (parallel and sequential)
4. Generate comprehensive reports

Usage:
    python tools/performance_tests/run_all_dataset_sizes.py
    python tools/performance_tests/run_all_dataset_sizes.py --sizes small medium
    python tools/performance_tests/run_all_dataset_sizes.py --skip-generation
"""

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

import logging  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


DATASET_SIZES = ["small", "medium", "large"]


def run_command(cmd: list[str], description: str) -> bool:
    """
    Run a command and log its output.

    Args:
        cmd: Command and arguments as list
        description: Description of what the command does

    Returns:
        True if successful, False otherwise
    """
    logger.info(f"\n{'=' * 80}")
    logger.info(f"Running: {description}")
    logger.info(f"Command: {' '.join(cmd)}")
    logger.info(f"{'=' * 80}\n")

    try:
        subprocess.run(  # noqa: S603
            cmd,
            check=True,
            capture_output=False,  # Stream output to console
            text=True,
        )
        logger.info(f"✓ {description} completed successfully")
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"✗ {description} failed with exit code {e.returncode}")
        return False


def generate_test_data(size: str, output_dir: Path) -> bool:
    """
    Generate test data for a specific size.

    Args:
        size: Dataset size (small, medium, large)
        output_dir: Directory for output files

    Returns:
        True if successful, False otherwise
    """
    stats_file = output_dir / f"generation_stats_{size}.json"

    cmd = [
        sys.executable,
        "tools/performance_tests/generate_test_data.py",
        "--size",
        size,
        "--output",
        str(stats_file),
    ]

    success = run_command(cmd, f"Generate {size} dataset")

    if success and stats_file.exists():
        with open(stats_file) as f:
            stats = json.load(f)
            logger.info(f"\nDataset {size} generated:")
            for dataset in stats.get("datasets", []):
                logger.info(
                    f"  Size: {dataset['size_name']}, "
                    f"Collections: {dataset['collections_created']}, "
                    f"Data: {dataset['total_data_size_mb']:.2f} MB"
                )

    return success


def run_individual_task_tests(size: str, output_dir: Path) -> bool:
    """
    Run individual task performance tests.

    Args:
        size: Dataset size being tested
        output_dir: Directory for output files

    Returns:
        True if successful, False otherwise
    """
    task_output_dir = output_dir / f"individual_tasks_{size}"

    cmd = [
        sys.executable,
        "tools/performance_tests/task_performance_test.py",
        "--task",
        "all",
        "--output-dir",
        str(task_output_dir),
    ]

    return run_command(cmd, f"Individual task tests ({size} dataset)")


def run_all_tasks_tests(size: str, output_dir: Path) -> bool:
    """
    Run all tasks together (parallel and sequential).

    Args:
        size: Dataset size being tested
        output_dir: Directory for output files

    Returns:
        True if successful, False otherwise
    """
    all_tasks_output_dir = output_dir / f"all_tasks_{size}"

    cmd = [
        sys.executable,
        "tools/performance_tests/run_all_tasks.py",
        "--mode",
        "both",  # Run both parallel and sequential
        "--output-dir",
        str(all_tasks_output_dir),
    ]

    return run_command(cmd, f"All tasks tests ({size} dataset)")


def generate_summary_report(output_dir: Path, sizes: list[str]) -> None:  # noqa: PLR0915
    """
    Generate a summary report across all dataset sizes.

    Args:
        output_dir: Base output directory
        sizes: List of dataset sizes tested
    """
    logger.info("\n" + "=" * 80)
    logger.info("GENERATING SUMMARY REPORT")
    logger.info("=" * 80)

    summary_file = output_dir / "SUMMARY.md"

    with open(summary_file, "w") as f:
        f.write("# Performance Test Summary\n\n")
        f.write(f"**Generated:** {datetime.now(UTC).isoformat()}\n\n")
        f.write("## Overview\n\n")
        f.write("This report summarizes performance testing across multiple dataset sizes.\n\n")

        # Link to individual reports
        f.write("## Detailed Reports by Dataset Size\n\n")
        for size in sizes:
            f.write(f"### {size.capitalize()} Dataset\n\n")

            # Generation stats
            stats_file = output_dir / f"generation_stats_{size}.json"
            if stats_file.exists():
                with open(stats_file) as sf:
                    stats = json.load(sf)
                    for dataset in stats.get("datasets", []):
                        f.write(f"- **Target Events:** {dataset['target_events']:,}\n")
                        f.write(f"- **Collections Created:** {dataset['collections_created']}\n")
                        f.write(f"- **Data Size:** {dataset['total_data_size_mb']:.2f} MB\n")
                        f.write(f"- **Generation Time:** {dataset['duration_seconds']:.2f}s\n")

            # Individual tasks report
            individual_report = output_dir / f"individual_tasks_{size}" / "report.md"
            if individual_report.exists():
                f.write(f"- [Individual Tasks Report](individual_tasks_{size}/report.md)\n")

            # All tasks report
            all_tasks_report = output_dir / f"all_tasks_{size}" / "report.md"
            if all_tasks_report.exists():
                f.write(f"- [All Tasks Report](all_tasks_{size}/report.md)\n")

            f.write("\n")

        # Comparison table
        f.write("## Performance Comparison\n\n")
        f.write(
            "| Dataset Size | Target Events | Data Size (MB) | Individual Tasks Time (s) | All Tasks Parallel (s) | All Tasks Sequential (s) |\n"
        )
        f.write(
            "|--------------|---------------|----------------|---------------------------|------------------------|-------------------------|\n"
        )

        for size in sizes:
            row = [size.capitalize()]

            # Get generation stats
            stats_file = output_dir / f"generation_stats_{size}.json"
            if stats_file.exists():
                with open(stats_file) as sf:
                    stats = json.load(sf)
                    dataset = stats.get("datasets", [{}])[0]
                    row.append(f"{dataset.get('target_events', 0):,}")
                    row.append(f"{dataset.get('total_data_size_mb', 0):.2f}")
            else:
                row.extend(["N/A", "N/A"])

            # Get individual tasks time
            individual_json = output_dir / f"individual_tasks_{size}" / "report.json"
            if individual_json.exists():
                with open(individual_json) as ij:
                    report = json.load(ij)
                    total_time = report.get("summary", {}).get("total_duration_seconds", 0)
                    row.append(f"{total_time:.2f}")
            else:
                row.append("N/A")

            # Get all tasks times
            all_tasks_json = output_dir / f"all_tasks_{size}" / "report.json"
            if all_tasks_json.exists():
                with open(all_tasks_json) as aj:
                    report = json.load(aj)
                    # Find parallel and sequential totals
                    parallel_time = "N/A"
                    sequential_time = "N/A"
                    for result in report.get("results", []):
                        if result["task_name"] == "ALL_TASKS_PARALLEL_TOTAL":
                            parallel_time = f"{result['duration_seconds']:.2f}"
                        elif result["task_name"] == "ALL_TASKS_SEQUENTIAL_TOTAL":
                            sequential_time = f"{result['duration_seconds']:.2f}"
                    row.append(parallel_time)
                    row.append(sequential_time)
            else:
                row.extend(["N/A", "N/A"])

            f.write("| " + " | ".join(row) + " |\n")

    logger.info(f"Summary report written to {summary_file}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Run automated performance tests across all dataset sizes")
    parser.add_argument(
        "--sizes",
        nargs="+",
        choices=DATASET_SIZES,
        default=DATASET_SIZES,
        help="Dataset sizes to test (default: all)",
    )
    parser.add_argument(
        "--skip-generation",
        action="store_true",
        help="Skip test data generation (use existing data)",
    )
    parser.add_argument(
        "--skip-individual",
        action="store_true",
        help="Skip individual task tests",
    )
    parser.add_argument(
        "--skip-all-tasks",
        action="store_true",
        help="Skip all tasks together tests",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Output directory for all results (default: auto-generated with timestamp)",
    )

    args = parser.parse_args()

    # Create output directory
    if args.output_dir:
        output_dir = args.output_dir
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = Path(f"tools/performance_tests/output/full_suite_{timestamp}")

    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"\n{'=' * 80}")
    logger.info("PERFORMANCE TEST SUITE")
    logger.info(f"{'=' * 80}")
    logger.info(f"Testing dataset sizes: {', '.join(args.sizes)}")
    logger.info(f"Output directory: {output_dir}")
    logger.info(f"{'=' * 80}\n")

    results = []

    for size in args.sizes:
        logger.info(f"\n{'#' * 80}")
        logger.info(f"# TESTING {size.upper()} DATASET")
        logger.info(f"{'#' * 80}\n")

        # Step 1: Generate test data
        if not args.skip_generation:
            success = generate_test_data(size, output_dir)
            results.append((f"Generate {size} data", success))
        else:
            logger.info(f"Skipping data generation for {size} (using existing data)")

        # Step 2: Run individual task tests
        if not args.skip_individual:
            success = run_individual_task_tests(size, output_dir)
            results.append((f"Individual tasks ({size})", success))

        # Step 3: Run all tasks together
        if not args.skip_all_tasks:
            success = run_all_tasks_tests(size, output_dir)
            results.append((f"All tasks ({size})", success))

    # Generate summary report
    generate_summary_report(output_dir, args.sizes)

    # Print final summary
    logger.info("\n" + "=" * 80)
    logger.info("FINAL SUMMARY")
    logger.info("=" * 80)

    for test_name, success in results:
        status = "✓" if success else "✗"
        logger.info(f"{status} {test_name}")

    total_tests = len(results)
    successful_tests = sum(1 for _, success in results if success)

    logger.info(f"\nTotal: {successful_tests}/{total_tests} tests successful")
    logger.info(f"Results saved to: {output_dir}")

    # Exit with error code if any tests failed
    if successful_tests < total_tests:
        sys.exit(1)


if __name__ == "__main__":
    main()
