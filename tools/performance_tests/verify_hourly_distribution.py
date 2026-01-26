#!/usr/bin/env python
"""
Verify that hourly collection test data is correctly distributed.

This script validates that generated test data meets quality requirements:
- Correct number of collections (72 = 24 hours × 3 collectors)
- Even distribution across hours
- Correct event counts per collection
- Total events match target dataset size

Usage:
    python tools/performance_tests/verify_hourly_distribution.py --size small
    python tools/performance_tests/verify_hourly_distribution.py --size medium
    python tools/performance_tests/verify_hourly_distribution.py --size large
    python tools/performance_tests/verify_hourly_distribution.py --size all
"""

import argparse
import os
import sys
from collections import defaultdict
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# Setup Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "metrics_service.settings")
import django  # noqa: E402

django.setup()

from generate_test_data import DATASET_SIZES  # noqa: E402
from perf_utils import logger  # noqa: E402

from apps.tasks.models import HourlyMetricsCollection  # noqa: E402


def verify_dataset(size_name: str) -> tuple[bool, dict]:  # noqa: C901, PLR0912, PLR0915
    """
    Verify a single dataset's distribution and correctness.

    Args:
        size_name: Dataset size name (small, medium, large)

    Returns:
        Tuple of (is_valid, validation_stats)
    """
    config = DATASET_SIZES[size_name]
    expected_events_per_hour = config["events_per_hour"]
    expected_total_events = config["target_events"]

    logger.info(f"\n{'=' * 80}")
    logger.info(f"VERIFYING {size_name.upper()} DATASET")
    logger.info(f"{'=' * 80}")
    logger.info(f"Expected total events: {expected_total_events:,}")
    logger.info(f"Expected events per hour per collector: {expected_events_per_hour:,}")

    # Fetch all collections
    collections = HourlyMetricsCollection.objects.all().order_by("collection_timestamp")
    total_collections = collections.count()

    logger.info(f"\nTotal collections found: {total_collections}")

    # Expected: 24 hours × 3 collectors = 72 collections
    expected_collections = 24 * 3
    is_valid = True
    issues = []

    # Check 1: Total collection count
    if total_collections != expected_collections:
        is_valid = False
        issues.append(
            f"Expected {expected_collections} collections (24 hours × 3 collectors), found {total_collections}"
        )
        logger.error(f"❌ Collection count mismatch: {issues[-1]}")
    else:
        logger.info(f"✓ Collection count correct: {total_collections}")

    # Check 2: Collector type distribution
    collector_counts = defaultdict(int)
    for collection in collections:
        collector_counts[collection.collector_type] += 1

    logger.info("\nCollector type distribution:")
    for collector_type, count in sorted(collector_counts.items()):
        logger.info(f"  {collector_type}: {count}")
        if count != 24:
            is_valid = False
            issues.append(f"{collector_type} has {count} collections, expected 24")
            logger.error(f"  ❌ Expected 24, found {count}")
        else:
            logger.info("  ✓ Correct count (24)")

    # Check 3: Hourly distribution
    hourly_distribution = defaultdict(int)
    for collection in collections:
        hour_key = collection.collection_timestamp.strftime("%Y-%m-%d %H:00")
        hourly_distribution[hour_key] += 1

    logger.info("\nHourly distribution (should be 3 per hour):")
    hours_with_issues = []
    for hour_key in sorted(hourly_distribution.keys()):
        count = hourly_distribution[hour_key]
        if count != 3:
            is_valid = False
            hours_with_issues.append(hour_key)
            issues.append(f"Hour {hour_key} has {count} collections, expected 3")
            logger.error(f"  {hour_key}: {count} ❌")
        else:
            logger.info(f"  {hour_key}: {count} ✓")

    if not hours_with_issues:
        logger.info(f"✓ All {len(hourly_distribution)} hours have correct distribution (3 collections each)")

    # Check 4: Event counts
    logger.info("\nEvent count verification:")
    total_events = 0
    event_count_issues = []

    for collection in collections:
        event_count = len(collection.raw_data.get("events", []))
        total_events += event_count

        # Allow 10% tolerance for event counts (random generation may vary)
        tolerance = expected_events_per_hour * 0.1
        if abs(event_count - expected_events_per_hour) > tolerance:
            event_count_issues.append(
                f"{collection.collector_type} at {collection.collection_timestamp}: "
                f"{event_count} events (expected ~{expected_events_per_hour})"
            )

    logger.info(f"Total events across all collections: {total_events:,}")
    logger.info(f"Expected total events: {expected_total_events:,}")

    # Allow 5% tolerance for total events
    total_tolerance = expected_total_events * 0.05
    if abs(total_events - expected_total_events) > total_tolerance:
        is_valid = False
        issues.append(f"Total events {total_events:,} differs from expected {expected_total_events:,} by more than 5%")
        logger.error(f"❌ Total event count mismatch: {issues[-1]}")
    else:
        logger.info("✓ Total event count within acceptable range")

    if event_count_issues:
        logger.warning("\nEvent count variations (within tolerance):")
        for issue in event_count_issues[:5]:  # Show first 5
            logger.warning(f"  {issue}")
        if len(event_count_issues) > 5:
            logger.warning(f"  ... and {len(event_count_issues) - 5} more")

    # Check 5: Data sizes
    logger.info("\nData size verification:")
    total_size_bytes = sum(c.data_size_bytes for c in collections)
    total_size_mb = total_size_bytes / (1024 * 1024)
    logger.info(f"Total data size: {total_size_mb:.2f} MB")

    # Check 6: Status verification
    logger.info("\nStatus verification:")
    status_counts = defaultdict(int)
    for collection in collections:
        status_counts[collection.status] += 1

    for status, count in sorted(status_counts.items()):
        logger.info(f"  {status}: {count}")

    # Accept both 'collected' and 'processed' as valid (processed = already used in tests)
    valid_statuses = ["collected", "processed"]
    valid_count = sum(status_counts.get(s, 0) for s in valid_statuses)

    if valid_count != total_collections:
        is_valid = False
        issues.append(
            f"Collections with invalid status: {total_collections - valid_count} "
            f"(expected all to be 'collected' or 'processed')"
        )
        logger.error(f"❌ Status issue: {issues[-1]}")
    else:
        logger.info("✓ All collections have valid status (collected or processed)")

    # Check 7: Time sequence (no gaps)
    logger.info("\nTime sequence verification:")

    # Group by collector type to check each stream
    collector_timestamps = defaultdict(list)
    for collection in collections:
        collector_timestamps[collection.collector_type].append(collection.collection_timestamp)

    gap_issues = []
    for collector_type, ts_list in collector_timestamps.items():
        sorted_ts = sorted(ts_list)
        for i in range(len(sorted_ts) - 1):
            gap = (sorted_ts[i + 1] - sorted_ts[i]).total_seconds() / 3600
            # Use tolerance for floating point comparison (allow 0.1% deviation)
            if abs(gap - 1.0) > 0.001:
                gap_issues.append(f"{collector_type}: {gap:.1f} hour gap between {sorted_ts[i]} and {sorted_ts[i + 1]}")

    if gap_issues:
        is_valid = False
        issues.extend(gap_issues)
        logger.error("❌ Time sequence gaps found:")
        for gap_issue in gap_issues:
            logger.error(f"  {gap_issue}")
    else:
        logger.info("✓ No gaps in time sequence (all hourly intervals correct)")

    # Summary
    logger.info(f"\n{'=' * 80}")
    if is_valid:
        logger.info(f"✓ VALIDATION PASSED for {size_name.upper()} dataset")
        logger.info(f"  Total collections: {total_collections}")
        logger.info(f"  Total events: {total_events:,}")
        logger.info(f"  Total size: {total_size_mb:.2f} MB")
    else:
        logger.error(f"❌ VALIDATION FAILED for {size_name.upper()} dataset")
        logger.error(f"Issues found ({len(issues)}):")
        for issue in issues:
            logger.error(f"  - {issue}")
    logger.info(f"{'=' * 80}\n")

    return is_valid, {
        "size": size_name,
        "valid": is_valid,
        "total_collections": total_collections,
        "expected_collections": expected_collections,
        "total_events": total_events,
        "expected_events": expected_total_events,
        "total_size_mb": total_size_mb,
        "collector_counts": dict(collector_counts),
        "status_counts": dict(status_counts),
        "issues": issues,
    }


def verify_all_datasets() -> dict[str, dict]:
    """
    Verify all dataset sizes.

    Returns:
        Dictionary of size -> validation stats
    """
    results = {}

    # First check if there's any data at all
    total_count = HourlyMetricsCollection.objects.count()
    if total_count == 0:
        logger.error("❌ No HourlyMetricsCollection records found in database!")
        logger.error("Please generate test data first using generate_test_data.py")
        return results

    logger.info(f"Found {total_count} total HourlyMetricsCollection records")
    logger.info("Attempting to identify dataset size...\n")

    # Try to identify which dataset this is based on total events
    sample_collection = HourlyMetricsCollection.objects.first()
    if sample_collection:
        events_per_collection = len(sample_collection.raw_data.get("events", []))

        # Match to dataset size
        for size_name, config in DATASET_SIZES.items():
            expected_per_hour = config["events_per_hour"]
            if abs(events_per_collection - expected_per_hour) < (expected_per_hour * 0.2):
                logger.info(f"Detected {size_name} dataset based on event count\n")
                is_valid, stats = verify_dataset(size_name)
                results[size_name] = stats
                break
        else:
            logger.warning(f"Could not identify dataset size. Sample collection has {events_per_collection} events")

    return results


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Verify hourly collection test data distribution and correctness")
    parser.add_argument(
        "--size",
        choices=list(DATASET_SIZES.keys()) + ["all"],
        default="all",
        help="Dataset size to verify (default: auto-detect)",
    )

    args = parser.parse_args()

    logger.info("=" * 80)
    logger.info("HOURLY COLLECTION DATA VERIFICATION")
    logger.info("=" * 80)

    if args.size == "all":
        results = verify_all_datasets()
    else:
        # Check if data exists
        count = HourlyMetricsCollection.objects.count()
        if count == 0:
            logger.error("❌ No HourlyMetricsCollection records found!")
            logger.error(f"Please generate {args.size} dataset first:")
            logger.error(f"  python tools/performance_tests/generate_test_data.py --size {args.size}")
            sys.exit(1)

        is_valid, stats = verify_dataset(args.size)
        results = {args.size: stats}

    # Overall summary
    if results:
        logger.info("\n" + "=" * 80)
        logger.info("OVERALL VERIFICATION SUMMARY")
        logger.info("=" * 80)

        all_valid = all(r["valid"] for r in results.values())

        for size_name, stats in results.items():
            status = "✓ PASS" if stats["valid"] else "❌ FAIL"
            logger.info(
                f"{size_name.upper()}: {status} - "
                f"{stats['total_collections']} collections, "
                f"{stats['total_events']:,} events, "
                f"{stats['total_size_mb']:.2f} MB"
            )

        logger.info("=" * 80)

        if all_valid:
            logger.info("\n✓ All datasets validated successfully!")
            sys.exit(0)
        else:
            logger.error("\n❌ Some datasets failed validation")
            sys.exit(1)
    else:
        logger.error("\n❌ No datasets found to verify")
        sys.exit(1)


if __name__ == "__main__":
    main()
