"""
Create daily summary from hourly collections.

This task aggregates metrics from all hourly collections for a given day,
collecting config data, and creating a comprehensive daily summary record.
"""

import logging
from datetime import date, datetime, timedelta
from typing import Any

from django.utils import timezone

from ..utils import (
    create_task_result,
    get_db_connection,
    log_task_execution,
    task,
    task_execution_wrapper,
)
from .helpers import DEFAULT_DB_NAME, METRICS_UTILITY_AVAILABLE, config

logger = logging.getLogger(__name__)


def _aggregate_collector_data(collections: list) -> dict:
    """
    Aggregate metrics from hourly collections.

    This function merges the actual raw data from all hourly collections
    for use in daily rollup and anonymization.

    Args:
        collections: List of HourlyMetricsCollection objects

    Returns:
        dict: Aggregated metrics containing:
            - records: Merged list of all records from hourly collections
            - total_records: Total count of records
            - hourly_snapshots: Metadata about each hourly collection
    """
    aggregated = {
        "records": [],
        "total_records": 0,
        "hourly_snapshots": [],
    }

    for collection in collections:
        data = collection.raw_data

        # Extract records from the raw data
        # csv_to_json returns {"records": [...], "total_records": N, "file_count": N}
        if isinstance(data, dict):
            records = data.get("records", [])
            record_count = len(records) if records else data.get("total_records", 0)
            # Merge records into aggregated list
            if records:
                aggregated["records"].extend(records)
        elif isinstance(data, list):
            # If raw_data is already a list, use it directly
            records = data
            record_count = len(data)
            aggregated["records"].extend(records)
        else:
            record_count = 0

        aggregated["total_records"] += record_count
        aggregated["hourly_snapshots"].append(
            {
                "hour": collection.collection_timestamp.hour,
                "collection_id": collection.id,
                "record_count": record_count,
                "timestamp": collection.collection_timestamp.isoformat(),
            }
        )

    return aggregated


@task(queue="metrics_collectors", decorate=False)
@task_execution_wrapper("daily_metrics_rollup")
def daily_metrics_rollup(**kwargs) -> dict[str, Any]:
    """
    Create daily summary from hourly collections.

    This task:
    1. Queries all hourly collections for the previous day
    2. Aggregates metrics (sums, averages, counts)
    3. Stores references to all 24 hourly snapshots
    4. Collects config data (once per day)
    5. Creates DailyMetricsSummary record

    Args:
        **kwargs: Task data containing:
            - summary_date (str): Date to summarize (YYYY-MM-DD, defaults to yesterday)
            - database (str): Database name (default: 'awx')

    Returns:
        dict: Task result with summary ID and statistics
    """
    from apps.tasks.models import DailyMetricsSummary, HourlyMetricsCollection

    # Determine summary date (default to yesterday)
    summary_date_str = kwargs.get("summary_date")
    if summary_date_str:
        summary_date = date.fromisoformat(summary_date_str)
    else:
        summary_date = timezone.now().date() - timedelta(days=1)

    log_task_execution("daily_metrics_rollup", "processing", f"Creating daily summary for: {summary_date}")

    try:
        # Query all hourly collections for this date
        start_datetime = timezone.make_aware(datetime.combine(summary_date, datetime.min.time()))
        end_datetime = start_datetime + timedelta(days=1)

        hourly_collections = HourlyMetricsCollection.objects.filter(
            collection_timestamp__gte=start_datetime, collection_timestamp__lt=end_datetime, status="collected"
        ).order_by("collector_type", "collection_timestamp")

        # Group by collector type
        collections_by_type: dict[str, list] = {}
        for collection in hourly_collections:
            if collection.collector_type not in collections_by_type:
                collections_by_type[collection.collector_type] = []
            collections_by_type[collection.collector_type].append(collection)

        # Build hourly collection IDs map
        hourly_collection_ids = {
            collector_type: [c.id for c in collections] for collector_type, collections in collections_by_type.items()
        }

        # Aggregate metrics for each collector type
        aggregated_metrics = {}
        missing_hours = []
        collector_types = ["job_host_summary", "main_host", "main_jobevent"]

        for collector_type in collector_types:
            collections = collections_by_type.get(collector_type, [])

            # Check for missing hours (should have 24 collections)
            if len(collections) < 24:
                collected_hours = {c.collection_timestamp.hour for c in collections}
                missing_hours.extend([f"{collector_type}:{hour}" for hour in range(24) if hour not in collected_hours])

            # Use the generic aggregator
            aggregated_metrics[collector_type] = _aggregate_collector_data(collections)

        # Collect config data (once per day)
        config_data = {}
        if METRICS_UTILITY_AVAILABLE:
            try:
                db_name = kwargs.get("database", DEFAULT_DB_NAME)
                db_connection = get_db_connection(db_name)
                config_collector = config(db=db_connection)
                config_data = config_collector.gather()
            except Exception as e:
                logger.error(f"Failed to collect config data: {str(e)}")
                config_data = {"error": str(e)}

        # Calculate count from the IDs we actually processed (not from a new query)
        # This avoids a race condition where new records could be inserted between
        # iteration and count/update, causing incorrect counts and marking unprocessed
        # records as "processed"
        all_processed_ids = []
        for ids_list in hourly_collection_ids.values():
            all_processed_ids.extend(ids_list)
        hourly_collections_count = len(all_processed_ids)

        # Create or update DailyMetricsSummary
        # Use update_or_create to handle retries and scheduler double-triggers gracefully
        # The unique constraint on summary_date would cause IntegrityError if we used
        # create() and a record already exists for this date
        daily_summary, created = DailyMetricsSummary.objects.update_or_create(
            summary_date=summary_date,
            defaults={
                "aggregated_metrics": aggregated_metrics,
                "hourly_collection_ids": hourly_collection_ids,
                "config_data": config_data,
                "status": "aggregated",
                "hourly_collections_count": hourly_collections_count,
                "missing_hours": missing_hours,
                "aggregation_completed_at": timezone.now(),
                "rollup_task_execution_id": kwargs.get("execution_id"),
                "error_message": "",  # Clear any previous error
            },
        )

        # Mark only the hourly collections we actually processed as "processed"
        # Uses the collected IDs to avoid race condition with newly inserted records
        HourlyMetricsCollection.objects.filter(id__in=all_processed_ids).update(status="processed")

        action = "Created" if created else "Updated"
        log_task_execution(
            "daily_metrics_rollup",
            "completed",
            f"{action} daily summary ID: {daily_summary.id} with {hourly_collections_count} hourly collections",
        )

        return create_task_result(
            "success",
            {
                "task_type": "daily_metrics_rollup",
                "summary_id": daily_summary.id,
                "summary_date": str(summary_date),
                "hourly_collections_count": hourly_collections_count,
                "missing_hours": missing_hours,
                "aggregated_collectors": list(aggregated_metrics.keys()),
                "created": created,  # True if new record, False if updated existing
            },
        )

    except Exception as e:
        logger.error(f"Error in daily_metrics_rollup: {str(e)}")
        return create_task_result("error", error=f"Rollup failed: {str(e)}")
