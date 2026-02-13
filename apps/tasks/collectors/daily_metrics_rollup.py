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
from .helpers import DEFAULT_DB_NAME, _compute_rollup_from_dataframe

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


@task(queue="metrics_collectors", decorate=False)
@task_execution_wrapper("daily_metrics_rollup")
def daily_metrics_rollup(**kwargs) -> dict[str, Any]:
    """
    Create daily summary from hourly rollups (REDUCE phase).

    This task:
    1. Queries all hourly rollup collections for the previous day
    2. Merges hourly rollups into daily rollups using rollup processor merge logic
    3. Collects unified_jobs data (once per day for the full day)
    4. Collects execution_environments snapshot (once per day)
    5. Collects config data (once per day)
    6. Collects main_host snapshot (once per day)
    7. Creates DailyMetricsSummary record with complete daily rollup

    Collectors:
        - Hourly merged: job_host_summary, main_jobevent
        - Daily collected: unified_jobs, execution_environments, config, main_host

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

    log_task_execution("daily_metrics_rollup", "processing", f"Creating daily rollup for: {summary_date}")

    try:
        # Import from metrics-utility (will fail if not available)
        from metrics_utility.anonymized_rollups.events_modules_anonymized_rollup import (
            EventModulesAnonymizedRollup as EventModulesRollupProcessor,
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
        from metrics_utility.library.collectors.controller import (
            config,
            execution_environments,
            main_host,
            unified_jobs,
        )

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

        # Rollup processors for each collector type
        rollup_processors = {
            "job_host_summary": JobHostSummaryRollupProcessor(),
            "main_jobevent": EventModulesRollupProcessor(),
            # main_host has no rollup processor - it's a snapshot
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

        # Collect config data (once per day)
        # OPTIMIZED: Direct data access (no CSV I/O)
        config_data = {}
        try:
            db_name = kwargs.get("database", DEFAULT_DB_NAME)
            db_connection = get_db_connection(db_name)
            config_collector = config(db=db_connection)
            config_data = config_collector.gather()
        except Exception as e:
            logger.error(f"Failed to collect config data: {str(e)}")
            config_data = {"error": str(e)}

        # Get main_host snapshot (latest from the day, or collect fresh)
        # OPTIMIZED: Direct data access (no CSV I/O)
        main_host_data = {}
        main_host_collections = collections_by_type.get("main_host", [])
        if main_host_collections:
            # Use the latest main_host snapshot from the day
            latest_main_host = main_host_collections[-1]
            main_host_data = latest_main_host.raw_data
        else:
            # Collect main_host fresh if not in hourly collections
            try:
                db_name = kwargs.get("database", DEFAULT_DB_NAME)
                db_connection = get_db_connection(db_name)

                main_host_collector = main_host(db=db_connection)
                records = main_host_collector.gather()
                main_host_data = {"records": records, "total_records": len(records)}
            except Exception as e:
                logger.error(f"Failed to collect main_host data: {str(e)}")
                main_host_data = {"error": str(e)}

        daily_rollup["main_host"] = main_host_data
        daily_rollup["config"] = config_data

        # Collect unified_jobs data (fresh daily for the full summary date)
        # OPTIMIZED: Direct data access (no CSV I/O)
        # This collector supports date ranges, so we collect for the entire day
        unified_jobs_data = {}
        try:
            db_name = kwargs.get("database", DEFAULT_DB_NAME)
            db_connection = get_db_connection(db_name)

            # Collect for the full day being summarized (start_datetime to end_datetime)
            unified_jobs_collector = unified_jobs(db=db_connection, since=start_datetime, until=end_datetime)
            dataframe = unified_jobs_collector.gather()

            # Compute rollup using JobsRollupProcessor
            unified_jobs_rollup = _compute_rollup_from_dataframe(dataframe, JobsRollupProcessor())
            unified_jobs_data = unified_jobs_rollup.get("json", {})

            jobs_total = unified_jobs_data.get("jobs_total", 0)
            logger.info(f"Collected unified_jobs data for {summary_date}: {jobs_total} jobs total")
        except Exception as e:
            logger.error(f"Failed to collect unified_jobs data: {str(e)}")
            unified_jobs_data = {"error": str(e)}

        # Collect execution_environments data (fresh daily snapshot)
        # OPTIMIZED: Direct data access (no CSV I/O)
        # This is a snapshot collector (no since/until support)
        execution_environments_data = {}
        try:
            db_name = kwargs.get("database", DEFAULT_DB_NAME)
            db_connection = get_db_connection(db_name)

            execution_environments_collector = execution_environments(db=db_connection)
            dataframe = execution_environments_collector.gather()

            # Compute rollup using ExecutionEnvironmentsRollupProcessor
            ee_rollup = _compute_rollup_from_dataframe(dataframe, ExecutionEnvironmentsRollupProcessor())
            execution_environments_data = ee_rollup.get("json", {})

            ee_total = execution_environments_data.get("EE_total", 0)
            logger.info(f"Collected execution_environments data for {summary_date}: {ee_total} EEs total")
        except Exception as e:
            logger.error(f"Failed to collect execution_environments data: {str(e)}")
            execution_environments_data = {"error": str(e)}

        daily_rollup["unified_jobs"] = unified_jobs_data
        daily_rollup["execution_environments"] = execution_environments_data

        # Calculate count from the IDs we actually processed
        all_processed_ids = []
        for ids_list in hourly_collection_ids.values():
            all_processed_ids.extend(ids_list)
        hourly_collections_count = len(all_processed_ids)

        # Create or update DailyMetricsSummary
        # Use update_or_create to handle retries and scheduler double-triggers gracefully
        daily_summary, created = DailyMetricsSummary.objects.update_or_create(
            summary_date=summary_date,
            defaults={
                "aggregated_metrics": daily_rollup,  # This now contains properly merged rollups
                "hourly_collection_ids": hourly_collection_ids,
                "config_data": config_data,  # Also stored separately for backward compatibility
                "status": "aggregated",
                "hourly_collections_count": hourly_collections_count,
                "missing_hours": missing_hours,
                "aggregation_completed_at": timezone.now(),
                "rollup_task_execution_id": kwargs.get("execution_id"),
                "error_message": "",  # Clear any previous error
            },
        )

        # Mark only the hourly collections we actually processed as "processed"
        HourlyMetricsCollection.objects.filter(id__in=all_processed_ids).update(status="processed")

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
