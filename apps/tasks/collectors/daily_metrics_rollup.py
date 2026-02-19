"""
Create daily summary from hourly rollups (REDUCE phase).

This task merges hourly rollup statistics into a daily summary,
collects daily data (unified_jobs, execution_environments, config),
and creates a comprehensive daily rollup record.
"""

import logging
from datetime import date, datetime, timedelta
from typing import Any

import pandas as pd
from django.utils import timezone

from ..utils import (
    create_task_result,
    get_db_connection,
    log_task_execution,
    task,
    task_execution_wrapper,
)
from .helpers import DEFAULT_DB_NAME

logger = logging.getLogger(__name__)


def _merge_rollup_dataframes(collections: list, rollup_processor) -> dict | None:
    """
    Merge hourly rollup data using the rollup processor's merge logic (REDUCE phase).

    Args:
        collections: List of HourlyMetricsCollection objects with rollup data
        rollup_processor: Rollup processor instance for merging

    Returns:
        dict: Merged rollup data structure (e.g., {'aggregated': df, 'total': int}), or None if no data
    """
    merged = None

    for collection in collections:
        rollup_data = collection.raw_data

        # Skip empty collections
        if not rollup_data:
            continue

        # CRITICAL: Convert serialized DataFrames (lists of dicts) back to pandas DataFrames
        # The rollup_data structure varies by collector type:
        # - job_host_summary: {'aggregated': [...], 'jobhostsummary_total': int}
        # - main_jobevent: {'task_summary': [...], 'event_total': int}
        #
        # During MAP phase (hourly collection), rollup processors return:
        #   {'json': {...}, 'rollup': {'aggregated': DataFrame, 'total': int}}
        # We store rollup['rollup'] which becomes {'aggregated': [...], 'total': int}
        # after JSON serialization (DataFrames -> lists of dicts)
        #
        # During REDUCE phase (this function), we must:
        # 1. Restore the DataFrames from lists of dicts
        # 2. Pass the ENTIRE dict structure to merge() (not individual DataFrames)
        #
        # This is critical because the utility library's merge() methods expect
        # the full structure with both DataFrames AND metadata (totals, etc.)
        rollup_data_restored = {}
        for key, value in rollup_data.items():
            if isinstance(value, list) and value:
                # Convert list of dicts back to DataFrame
                rollup_data_restored[key] = pd.DataFrame(value)
            else:
                # Preserve scalars (totals, etc.)
                rollup_data_restored[key] = value

        # Pass the ENTIRE rollup structure to merge (not individual DataFrames)
        # The rollup processor's merge() method expects the full dict structure
        # with both DataFrames and metadata (totals, etc.)
        merged = rollup_processor.merge(merged, rollup_data_restored)

    return merged


def _aggregate_collector_rollups(collections: list, rollup_processor) -> dict:
    """
    Aggregate rollup statistics from hourly collections (REDUCE phase).

    This function merges hourly rollup statistics using the rollup processor's
    merge logic to produce a daily rollup.

    Args:
        collections: List of HourlyMetricsCollection objects with rollup data
        rollup_processor: Rollup processor instance (e.g., JobsRollupProcessor())

    Returns:
        dict: Daily rollup result with merged statistics
    """
    # Merge all hourly rollup data structures (REDUCE phase)
    merged_rollup = _merge_rollup_dataframes(collections, rollup_processor)

    # Compute final daily rollup statistics
    # The merged_rollup is a dict structure like {'aggregated': df, 'total': int}
    # which is exactly what base() expects
    if merged_rollup is not None:
        rollup_result = rollup_processor.base(merged_rollup)
        return rollup_result.get("json", {})

    # Return empty result if no data
    return {}


def _collect_and_group_hourly_collections(summary_date: date) -> tuple[dict[str, list], datetime, datetime]:
    """
    Query and group hourly collections by collector type.

    Args:
        summary_date: Date to query collections for

    Returns:
        tuple: (collections_by_type dict, start_datetime, end_datetime)
    """
    from apps.tasks.models import HourlyMetricsCollection

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

    return collections_by_type, start_datetime, end_datetime


def _merge_hourly_rollups(collections_by_type: dict[str, list]) -> tuple[dict, list]:
    """
    Merge hourly rollups into daily rollups using rollup processors.

    Args:
        collections_by_type: Dict mapping collector type to list of HourlyMetricsCollection objects

    Returns:
        tuple: (daily_rollup dict, missing_hours list)
    """
    from metrics_utility.anonymized_rollups.credentials_anonymized_rollup import (
        CredentialsAnonymizedRollup as CredentialsRollupProcessor,
    )
    from metrics_utility.anonymized_rollups.execution_environments_anonymized_rollup import (
        ExecutionEnvironmentsAnonymizedRollup as ExecutionEnvironmentsRollupProcessor,
    )
    from metrics_utility.anonymized_rollups.jobhostsummary_anonymized_rollup import (
        JobHostSummaryAnonymizedRollup as JobHostSummaryRollupProcessor,
    )
    from metrics_utility.anonymized_rollups.jobs_anonymized_rollup import (
        JobsAnonymizedRollup as JobsRollupProcessor,
    )

    # Rollup processors for each collector type
    rollup_processors = {
        "job_host_summary_service": JobHostSummaryRollupProcessor(),
        # Note: main_jobevent/EventModulesRollupProcessor removed (temporarily removed)
        "unified_jobs": JobsRollupProcessor(),
        "credentials_service": CredentialsRollupProcessor(),
        "execution_environments": ExecutionEnvironmentsRollupProcessor(),
    }

    # Merge hourly rollups into daily rollups (REDUCE phase)
    daily_rollup = {}
    missing_hours = []

    for collector_type, processor in rollup_processors.items():
        collections = collections_by_type.get(collector_type, [])

        # Check for missing hours (should have 24 collections for hourly collectors)
        if len(collections) < 24:
            collected_hours = {c.collection_timestamp.hour for c in collections}
            missing_hours.extend([f"{collector_type}:{hour}" for hour in range(24) if hour not in collected_hours])

        # Merge hourly rollups using rollup processor
        daily_rollup[collector_type] = _aggregate_collector_rollups(collections, processor)

    return daily_rollup, missing_hours


def _collect_config_data(db_name: str) -> dict:
    """
    Collect config data snapshot.

    Args:
        db_name: Database name

    Returns:
        dict: Config data or error dict
    """
    from metrics_utility.library.collectors.controller import config

    try:
        db_connection = get_db_connection(db_name)
        config_collector = config(db=db_connection)
        return config_collector.gather()
    except Exception as e:
        logger.error(f"Failed to collect config data: {str(e)}")
        return {"error": str(e)}


def _save_daily_summary(
    summary_date: date,
    daily_rollup: dict,
    collections_by_type: dict[str, list],
    config_data: dict,
    missing_hours: list,
    execution_id: str | None,
) -> tuple:
    """
    Create or update DailyMetricsSummary record.

    Args:
        summary_date: Date being summarized
        daily_rollup: Aggregated daily rollup data
        collections_by_type: Collections grouped by type
        config_data: Config data
        missing_hours: List of missing hourly collections
        execution_id: Task execution ID

    Returns:
        tuple: (daily_summary object, created boolean, hourly_collections_count)
    """
    from apps.tasks.models import DailyMetricsSummary, HourlyMetricsCollection

    # Build hourly collection IDs map
    hourly_collection_ids = {
        collector_type: [c.id for c in collections] for collector_type, collections in collections_by_type.items()
    }

    # Calculate count from the IDs we actually processed
    all_processed_ids = []
    for ids_list in hourly_collection_ids.values():
        all_processed_ids.extend(ids_list)
    hourly_collections_count = len(all_processed_ids)

    # Create or update DailyMetricsSummary
    daily_summary, created = DailyMetricsSummary.objects.update_or_create(
        summary_date=summary_date,
        defaults={
            "aggregated_metrics": daily_rollup,
            "hourly_collection_ids": hourly_collection_ids,
            "config_data": config_data,
            "status": "aggregated",
            "hourly_collections_count": hourly_collections_count,
            "missing_hours": missing_hours,
            "aggregation_completed_at": timezone.now(),
            "rollup_task_execution_id": execution_id,
            "error_message": "",  # Clear any previous error
        },
    )

    # Mark only the hourly collections we actually processed as "processed"
    HourlyMetricsCollection.objects.filter(id__in=all_processed_ids).update(status="processed")

    return daily_summary, created, hourly_collections_count


@task(queue="metrics_collectors", decorate=False)
@task_execution_wrapper("daily_metrics_rollup")
def daily_metrics_rollup(**kwargs) -> dict[str, Any]:
    """
    Create daily summary from hourly rollups (REDUCE phase).

    This task:
    1. Queries all hourly rollup collections for the previous day
    2. Merges hourly rollups into daily rollups using rollup processor merge logic
    3. Collects config data (simple inline snapshot)
    4. Creates DailyMetricsSummary record with complete daily rollup

    Collectors:
        - Hourly merged (from HourlyMetricsCollection):
            - job_host_summary_service
            - unified_jobs
            - credentials_service
        - Daily merged (from HourlyMetricsCollection):
            - execution_environments
        - Daily inline:
            - config

    Note: main_host (not in anonymized chain) and main_jobevent (temporarily removed)

    Args:
        **kwargs: Task data containing:
            - summary_date (str): Date to summarize (YYYY-MM-DD, defaults to yesterday)
            - database (str): Database name (default: 'awx')

    Returns:
        dict: Task result with summary ID and statistics
    """
    # Determine summary date (default to yesterday)
    summary_date_str = kwargs.get("summary_date")
    if summary_date_str:
        summary_date = date.fromisoformat(summary_date_str)
    else:
        summary_date = timezone.now().date() - timedelta(days=1)

    log_task_execution("daily_metrics_rollup", "processing", f"Creating daily rollup for: {summary_date}")

    try:
        db_name = kwargs.get("database", DEFAULT_DB_NAME)

        # Query and group hourly collections by type
        collections_by_type, start_datetime, end_datetime = _collect_and_group_hourly_collections(summary_date)

        # Merge hourly rollups into daily rollups (REDUCE phase)
        daily_rollup, missing_hours = _merge_hourly_rollups(collections_by_type)

        # Collect config data (still inline since it's a simple snapshot)
        config_data = _collect_config_data(db_name)
        daily_rollup["config"] = config_data

        # Note: unified_jobs, execution_environments, and credentials_service are now
        # collected by dedicated tasks and merged via _merge_hourly_rollups() above.
        # main_host removed (not used in anonymized chain).

        # Save daily summary and update hourly collection status
        daily_summary, created, hourly_collections_count = _save_daily_summary(
            summary_date, daily_rollup, collections_by_type, config_data, missing_hours, kwargs.get("execution_id")
        )

        action = "Created" if created else "Updated"
        log_task_execution(
            "daily_metrics_rollup",
            "completed",
            f"{action} daily rollup ID: {daily_summary.id} with {hourly_collections_count} hourly collections",
        )

        return create_task_result(
            "success",
            {
                "task_type": "daily_metrics_rollup",
                "summary_id": daily_summary.id,
                "summary_date": str(summary_date),
                "hourly_collections_count": hourly_collections_count,
                "missing_hours": missing_hours,
                "aggregated_collectors": list(daily_rollup.keys()),
                "created": created,  # True if new record, False if updated existing
            },
        )

    except Exception as e:
        logger.error(f"Error in daily_metrics_rollup: {str(e)}")
        return create_task_result("error", error=f"Rollup failed: {str(e)}")
