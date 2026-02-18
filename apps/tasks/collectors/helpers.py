"""
Shared helper functions for metrics collection tasks.

This module contains helper functions used by multiple collector tasks.
Single-use helpers remain with their respective task implementations.

Note: Tasks using metrics-utility will fail if it's not available. This is intentional -
the task runner handles exceptions and logs errors appropriately.
"""

import contextlib
import logging
from datetime import timedelta
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)

# Constants
UTC_OFFSET_SUFFIX = "+00:00"
DEFAULT_DB_NAME = "awx"

# Note: Rollup processors and collectors are imported inside tasks that need them
# This allows tasks to fail fast with clear error messages if metrics-utility is not available


# =============================================================================
# Shared Helper Functions
# =============================================================================


def _compute_rollup_from_dataframe(dataframe, rollup_processor) -> dict[str, Any]:
    """
    Compute rollup statistics from DataFrame directly (no CSV I/O).

    This is the OPTIMIZED version that eliminates CSV write/read/delete overhead.
    Used when collectors return DataFrames directly via output_mode='dataframe'.

    Args:
        dataframe: pandas DataFrame from collector (already loaded from DB)
        rollup_processor: Rollup processor instance (e.g., JobsRollupProcessor())

    Returns:
        dict: Rollup result with 'json' and 'rollup' keys
            - 'json': Aggregated statistics as dict
            - 'rollup': Intermediate dataframes for merging
    """
    # Prepare dataframe for rollup processing (inline trivial helper)
    # If dataframe is None or empty, skip preparation; otherwise call prepare()
    rollup_dataframe = None if dataframe is None or dataframe.empty else rollup_processor.prepare(dataframe)

    # Compute aggregated statistics
    rollup_result = rollup_processor.base(rollup_dataframe)

    return rollup_result


def _collect_hourly_metrics(
    collector_name: str,
    collector_func,
    rollup_processor,
    task_name: str,
    uses_date_range: bool = True,
    **kwargs,
) -> dict[str, Any]:
    """
    Generic helper for hourly metrics collection with rollup computation (MAP phase).

    This function:
    1. Collects raw CSV data from the AWX database
    2. Computes rollup statistics immediately (map phase)
    3. Stores only the rollup statistics (not raw rows) to save space

    Used by: collect_job_host_summary_hourly, collect_host_metrics_hourly, collect_main_host_hourly

    Args:
        collector_name: Name of the collector type (e.g., "job_host_summary")
        collector_func: The collector class/function to instantiate
        rollup_processor: Rollup processor instance for computing stats
        task_name: Name of the task for logging
        uses_date_range: Whether the collector accepts since/until parameters
        **kwargs: Task parameters

    Returns:
        dict: Task result with collection status
    """
    from django.utils import timezone

    from apps.tasks.models import HourlyMetricsCollection

    from ..utils import (
        create_task_result,
        get_db_connection,
        log_task_execution,
        parse_datetime_string,
    )

    # Determine collection hour (default to previous hour)
    hour_timestamp_str = kwargs.get("hour_timestamp")
    collection_hour = None
    if hour_timestamp_str:
        collection_hour = parse_datetime_string(hour_timestamp_str)
    # Fallback to previous hour if no timestamp provided or parsing failed
    if collection_hour is None:
        now = timezone.now()
        collection_hour = now.replace(minute=0, second=0, microsecond=0) - timedelta(hours=1)

    log_task_execution(task_name, "processing", f"Collecting {collector_name} for hour: {collection_hour.isoformat()}")

    try:
        db_name = kwargs.get("database", DEFAULT_DB_NAME)
        db_connection = get_db_connection(db_name)

        # Build collector parameters
        if uses_date_range:
            since = collection_hour
            until = collection_hour + timedelta(hours=1)
            collector = collector_func(db=db_connection, since=since, until=until)
            collection_params = {
                "database": db_name,
                "since": since.isoformat(),
                "until": until.isoformat(),
            }
        else:
            collector = collector_func(db=db_connection)
            collection_params = {
                "database": db_name,
                "collection_time": collection_hour.isoformat(),
            }

        # OPTIMIZED: Direct data access (no CSV I/O)
        # Collectors now always return DataFrame or dict directly
        data = collector.gather()

        if rollup_processor:
            # For rollup processors: data is a DataFrame
            rollup_result = _compute_rollup_from_dataframe(data, rollup_processor)
            # Extract the rollup data (intermediate format for merging)
            rollup_data = rollup_result.get("rollup", {})
        else:
            # For snapshot collectors without rollup: data is a DataFrame or dict
            # - main_host: returns DataFrame
            # - config: returns dict
            # Store the data with appropriate total_records count
            if isinstance(data, pd.DataFrame):
                total_records = len(data)  # Number of rows in DataFrame
            elif isinstance(data, list):
                total_records = len(data)  # Number of items in list
            elif isinstance(data, dict):
                total_records = 1  # Single dict object
            else:
                total_records = 1  # Fallback for unknown types

            rollup_data = {
                "records": data,
                "total_records": total_records,
            }

        # Store in HourlyMetricsCollection
        # Use update_or_create to handle retries and scheduler double-triggers
        # The unique_together constraint on (collector_type, collection_timestamp)
        # would cause IntegrityError if we used create() and a record already exists
        hourly_collection, created = HourlyMetricsCollection.objects.update_or_create(
            collector_type=collector_name,
            collection_timestamp=collection_hour,
            defaults={
                "raw_data": rollup_data,  # Store rollup, not raw CSV data
                "status": "collected",
                "collection_parameters": collection_params,
                "task_execution_id": kwargs.get("execution_id"),
                "error_message": "",  # Clear any previous error
            },
        )

        action = "Created" if created else "Updated"
        log_task_execution(task_name, "completed", f"{action} hourly collection ID: {hourly_collection.id}")

        return create_task_result(
            "success",
            {
                "task_type": task_name,
                "collector_type": collector_name,
                "collection_id": hourly_collection.id,
                "collection_timestamp": collection_hour.isoformat(),
                "data_size_bytes": hourly_collection.data_size_bytes,
                "was_retry": not created,
            },
        )

    except Exception as e:
        logger.error(f"Error in {task_name}: {str(e)}")

        # Store failed collection
        # Use update_or_create to handle cases where a record already exists
        # (e.g., a previous attempt created a record, or scheduler double-trigger)
        with contextlib.suppress(Exception):
            HourlyMetricsCollection.objects.update_or_create(
                collector_type=collector_name,
                collection_timestamp=collection_hour,
                defaults={
                    "raw_data": {},
                    "status": "failed",
                    "error_message": str(e),
                    "collection_parameters": {"database": kwargs.get("database", DEFAULT_DB_NAME)},
                },
            )

        return create_task_result("error", error=f"Collection failed: {str(e)}")
