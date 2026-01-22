#!/usr/bin/env python
"""
Generate test data for performance testing.

Creates HourlyMetricsCollection records with varying sizes:
- Small: ~100K events
- Medium: ~1M events
- Large: ~10M events

Usage:
    python tools/performance_tests/generate_test_data.py --size small
    python tools/performance_tests/generate_test_data.py --size medium
    python tools/performance_tests/generate_test_data.py --size large
    python tools/performance_tests/generate_test_data.py --size all
"""

import argparse
import json
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# Setup Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "metrics_service.settings")
import django  # noqa: E402

django.setup()

from perf_utils import PerformanceTimer, format_iso8601_timestamp, logger  # noqa: E402

from apps.tasks.models import DailyMetricsSummary, HourlyMetricsCollection  # noqa: E402

# Data size configurations
DATASET_SIZES = {
    "small": {
        "target_events": 100_000,
        "events_per_hour": 4_167,  # ~100K / 24 hours
        "description": "Small dataset (~100K events)",
    },
    "medium": {
        "target_events": 1_000_000,
        "events_per_hour": 41_667,  # ~1M / 24 hours
        "description": "Medium dataset (~1M events)",
    },
    "large": {
        "target_events": 10_000_000,
        "events_per_hour": 416_667,  # ~10M / 24 hours
        "description": "Large dataset (~10M events)",
    },
}


def generate_event_record(event_id: int) -> dict:
    """
    Generate a single event record with realistic structure.

    Args:
        event_id: Unique event identifier

    Returns:
        Dictionary representing an event
    """
    return {
        "id": event_id,
        "created": format_iso8601_timestamp(),
        "modified": format_iso8601_timestamp(),
        "event": "runner_on_ok",
        "event_data": {
            "host": f"host-{event_id % 100}",
            "task": f"task-{event_id % 50}",
            "res": {"changed": event_id % 2 == 0, "failed": event_id % 10 == 0},
        },
        "failed": event_id % 10 == 0,
        "changed": event_id % 2 == 0,
        "uuid": f"event-uuid-{event_id:08d}",
        "parent_uuid": f"parent-uuid-{event_id // 10:08d}",
        "counter": event_id,
        "stdout": f"Output from event {event_id}",
        "verbosity": 0,
        "start_line": event_id * 10,
        "end_line": (event_id + 1) * 10,
    }


def generate_hourly_collection_data(collector_type: str, events_per_hour: int, hour_offset: int) -> dict:
    """
    Generate data for a single hourly collection.

    Args:
        collector_type: Type of collector (job_host_summary, main_jobevent, main_host)
        events_per_hour: Number of events to generate
        hour_offset: Hour offset from now (for timestamp)

    Returns:
        Dictionary with collection data
    """
    base_event_id = hour_offset * 1_000_000  # Ensure unique IDs across hours

    if collector_type == "main_jobevent":
        # Generate event records
        records = [generate_event_record(base_event_id + i) for i in range(events_per_hour)]
        return {"events": records, "total_count": events_per_hour}

    elif collector_type == "job_host_summary":
        # Generate job host summary records
        num_hosts = min(100, events_per_hour // 10)
        records = []
        for i in range(num_hosts):
            records.append(
                {
                    "host_id": i,
                    "host_name": f"host-{i}",
                    "ok_count": events_per_hour // num_hosts,
                    "changed_count": (events_per_hour // num_hosts) // 2,
                    "failed_count": (events_per_hour // num_hosts) // 10,
                    "skipped_count": 0,
                    "total_count": events_per_hour // num_hosts,
                }
            )
        return {"job_host_summaries": records, "total_hosts": num_hosts}

    elif collector_type == "main_host":
        # Generate host configuration data
        num_hosts = min(100, max(10, events_per_hour // 100))
        records = []
        for i in range(num_hosts):
            records.append(
                {
                    "id": i,
                    "hostname": f"host-{i}",
                    "description": f"Test host {i}",
                    "enabled": True,
                    "instance_id": f"instance-{i}",
                    "variables": {"ansible_host": f"192.168.1.{i}"},
                }
            )
        return {"hosts": records, "total_hosts": num_hosts}

    else:
        return {}


def create_hourly_collections(size_name: str, cleanup_existing: bool = True) -> dict:
    """
    Create hourly collection records for 24 hours.

    Args:
        size_name: Dataset size name (small, medium, large)
        cleanup_existing: Whether to delete existing test data first

    Returns:
        Dictionary with creation statistics
    """
    config = DATASET_SIZES[size_name]
    events_per_hour = config["events_per_hour"]

    logger.info(f"Creating {config['description']}")
    logger.info(f"Target: {config['target_events']:,} events")
    logger.info(f"Events per hour: {events_per_hour:,}")

    # Cleanup existing data if requested
    if cleanup_existing:
        logger.info("Cleaning up existing test data...")
        with PerformanceTimer("cleanup_existing_data"):
            deleted_hourly = HourlyMetricsCollection.objects.all().delete()[0]
            deleted_daily = DailyMetricsSummary.objects.all().delete()[0]
            logger.info(f"Deleted {deleted_hourly} hourly collections, {deleted_daily} daily summaries")

    # Create collections for 24 hours
    base_timestamp = datetime.now(UTC).replace(minute=0, second=0, microsecond=0) - timedelta(days=1)

    collections_created = 0
    total_data_size = 0

    collector_types = ["main_jobevent", "job_host_summary", "main_host"]

    with PerformanceTimer(f"create_hourly_collections_{size_name}") as timer:
        for hour in range(24):
            collection_time = base_timestamp + timedelta(hours=hour)

            for collector_type in collector_types:
                # Generate data
                raw_data = generate_hourly_collection_data(collector_type, events_per_hour, hour)

                # Create collection record
                collection = HourlyMetricsCollection.objects.create(
                    collector_type=collector_type,
                    collection_timestamp=collection_time,
                    raw_data=raw_data,
                    status="collected",
                    collection_parameters={
                        "database": "default",
                        "since": (collection_time - timedelta(hours=1)).isoformat(),
                        "until": collection_time.isoformat(),
                    },
                )

                collections_created += 1
                total_data_size += collection.data_size_bytes

                if collections_created % 10 == 0:
                    logger.info(
                        f"Created {collections_created}/72 collections ({total_data_size / 1024 / 1024:.2f} MB)"
                    )

    stats = {
        "size_name": size_name,
        "target_events": config["target_events"],
        "events_per_hour": events_per_hour,
        "collections_created": collections_created,
        "total_data_size_bytes": total_data_size,
        "total_data_size_mb": total_data_size / 1024 / 1024,
        "duration_seconds": timer.metrics.duration_seconds,
        "memory_delta_mb": timer.metrics.memory_delta_mb,
    }

    logger.info(
        f"\nData generation complete for {size_name}:\n"
        f"  Collections: {collections_created}\n"
        f"  Total size: {stats['total_data_size_mb']:.2f} MB\n"
        f"  Duration: {stats['duration_seconds']:.2f}s\n"
        f"  Memory delta: {stats['memory_delta_mb']:+.2f} MB"
    )

    return stats


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Generate test data for performance testing")
    parser.add_argument(
        "--size",
        choices=["small", "medium", "large", "all"],
        required=True,
        help="Dataset size to generate",
    )
    parser.add_argument(
        "--keep-existing",
        action="store_true",
        help="Keep existing data (don't cleanup before generating)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Output file for generation statistics (JSON)",
    )

    args = parser.parse_args()

    all_stats = []

    sizes = ["small", "medium", "large"] if args.size == "all" else [args.size]

    cleanup_existing = not args.keep_existing
    for size in sizes:
        stats = create_hourly_collections(size, cleanup_existing=cleanup_existing)
        all_stats.append(stats)
        # Only cleanup before first dataset
        cleanup_existing = False

    # Write statistics if output specified
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, "w") as f:
            json.dump(
                {
                    "generated_at": format_iso8601_timestamp(),
                    "datasets": all_stats,
                },
                f,
                indent=2,
            )
        logger.info(f"Statistics written to {args.output}")


if __name__ == "__main__":
    main()
