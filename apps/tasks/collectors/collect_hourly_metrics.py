"""
Hourly metrics collector for time-series data.

Collects metrics for a specific hour, computes rollup statistics,
and stores in HourlyMetricsCollection.
"""

import logging
from datetime import datetime, timedelta
from typing import Any

from django.utils import timezone
from metrics_utility.anonymized_rollups.credentials_anonymized_rollup import (
    CredentialsAnonymizedRollup,
)
from metrics_utility.anonymized_rollups.events_modules_anonymized_rollup import (
    EventModulesAnonymizedRollup,
)
from metrics_utility.anonymized_rollups.jobhostsummary_anonymized_rollup import (
    JobHostSummaryAnonymizedRollup,
)
from metrics_utility.anonymized_rollups.jobs_anonymized_rollup import (
    JobsAnonymizedRollup,
)
from metrics_utility.library.collectors.controller import (
    credentials_service,
    job_host_summary_service,
    main_jobevent,
    unified_jobs,
)

from ..utils import create_task_result, get_db_connection, log_task_execution, task, task_execution_wrapper

logger = logging.getLogger(__name__)

DEFAULT_DB_NAME = "awx"

# Registry mapping collector_type to (collector_func, rollup_processor_class)
HOURLY_COLLECTORS = {
    "job_host_summary_service": {
        "collector_func": job_host_summary_service,
        "rollup_processor": JobHostSummaryAnonymizedRollup,
        "description": "Job host summary metrics (partition-optimized)",
    },
    "unified_jobs": {
        "collector_func": unified_jobs,
        "rollup_processor": JobsAnonymizedRollup,
        "description": "Unified jobs metrics",
    },
    "credentials_service": {
        "collector_func": credentials_service,
        "rollup_processor": CredentialsAnonymizedRollup,
        "description": "Credentials usage metrics",
    },
    "job_events": {
        "collector_func": main_jobevent,
        "rollup_processor": EventModulesAnonymizedRollup,
        "description": "Job events (event modules) metrics",
    },
}


@task(queue="metrics_collectors", decorate=False)
@task_execution_wrapper("collect_hourly_metrics")
def collect_hourly_metrics(**kwargs) -> dict[str, Any]:
    """
    Collect hourly metrics for a specific collector type.

    This function handles all time-series collectors that gather data
    for a specific hour window. It collects raw data, computes rollup
    statistics, and stores only the rollup in HourlyMetricsCollection.

    Args:
        **kwargs: Task data containing:
            - collector_type (str): Type of collector (required)
            - hour_timestamp (str): ISO timestamp for the hour to collect (optional, defaults to previous hour)
            - database (str): Database name (default: 'awx')

    Returns:
        dict: Task result with collection status and record ID

    Raises:
        ValueError: If collector_type is missing or invalid
    """
    from apps.tasks.models import HourlyMetricsCollection

    collector_type = kwargs.pop("collector_type", None)
    if not collector_type:
        raise ValueError("collector_type parameter is required")

    if collector_type not in HOURLY_COLLECTORS:
        valid_types = ", ".join(sorted(HOURLY_COLLECTORS.keys()))
        raise ValueError(f"Unknown collector_type: {collector_type}. Valid types: {valid_types}")

    config = HOURLY_COLLECTORS[collector_type]
    collector_func = config["collector_func"]
    rollup_processor_class = config["rollup_processor"]

    db_name = kwargs.get("database", DEFAULT_DB_NAME)

    # Determine hour to collect (default to previous full hour)
    hour_timestamp_str = kwargs.get("hour_timestamp")
    if hour_timestamp_str:
        hour_timestamp = datetime.fromisoformat(hour_timestamp_str)
    else:
        now = timezone.now()
        hour_timestamp = now.replace(minute=0, second=0, microsecond=0) - timedelta(hours=1)

    start_datetime = hour_timestamp
    end_datetime = start_datetime + timedelta(hours=1)

    log_task_execution(
        f"collect_{collector_type}",
        "processing",
        f"Collecting {collector_type} for hour: {start_datetime}",
    )

    try:
        # Get database connection
        db_connection = get_db_connection(db_name)

        # Collect data from AWX database for the hour window
        collector = collector_func(db=db_connection, since=start_datetime, until=end_datetime)
        dataframe = collector.gather()

        # Compute rollup statistics
        rollup_processor = rollup_processor_class()
        rollup_result = rollup_processor.prepare_base(dataframe)

        # Extract rollup data from result
        # The rollup_result structure varies by processor but typically has 'json' and 'rollup' keys
        if isinstance(rollup_result, dict):
            rollup_data = rollup_result.get("json") or rollup_result.get("rollup") or rollup_result
        else:
            rollup_data = rollup_result

        # Create or update HourlyMetricsCollection record
        collection, created = HourlyMetricsCollection.objects.update_or_create(
            collector_type=collector_type,
            collection_timestamp=start_datetime,
            defaults={
                "raw_data": rollup_data,
                "collection_completed_at": timezone.now(),
            },
        )

        action = "Created" if created else "Updated"
        log_task_execution(
            f"collect_{collector_type}",
            "completed",
            f"{action} hourly collection ID: {collection.id} for {start_datetime}",
        )

        return create_task_result(
            status="success",
            message=f"{action} hourly collection for {collector_type}",
            task_type=f"collect_{collector_type}",
            collection_id=collection.id,
            collector_type=collector_type,
            hour_timestamp=start_datetime.isoformat(),
        )

    except Exception as e:
        logger.exception(f"Failed to collect {collector_type} hourly metrics: {str(e)}")
        return create_task_result(
            status="error",
            message=f"Collection failed: {str(e)}",
            task_type=f"collect_{collector_type}",
            collector_type=collector_type,
        )
