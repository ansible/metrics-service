"""
Hourly metrics collector for time-series data.

Collects metrics for a specific hour, computes rollup statistics,
and stores in HourlyMetricsCollection.
"""

import logging
from datetime import datetime, timedelta
from typing import Any

from django.utils import timezone
from metrics_utility.anonymized_rollups import (
    CredentialsAnonymizedRollup,
    EventModulesAnonymizedRollup,
    JobHostSummaryAnonymizedRollup,
    JobsAnonymizedRollup,
)
from metrics_utility.library.collectors.controller import (
    credentials_service,
    job_host_summary_service,
    main_jobevent_service,
    unified_jobs,
)

from ..utils import generic_collect_metrics, get_db_connection, task, task_execution_wrapper

logger = logging.getLogger(__name__)

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
    "main_jobevent_service": {
        "collector_func": main_jobevent_service,
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
    collector_type = kwargs.pop("collector_type", None)
    if not collector_type:
        raise ValueError("collector_type parameter is required")

    # Determine hour to collect (default to previous full hour)
    hour_timestamp_str = kwargs.get("hour_timestamp")
    if hour_timestamp_str:
        hour_timestamp = datetime.fromisoformat(hour_timestamp_str)
    else:
        now = timezone.now()
        hour_timestamp = now.replace(minute=0, second=0, microsecond=0) - timedelta(hours=1)

    start_datetime = hour_timestamp
    end_datetime = start_datetime + timedelta(hours=1)

    # Get database connection
    db_connection = get_db_connection()

    # Use generic collector with hourly-specific time window
    return generic_collect_metrics(
        collector_type=collector_type,
        collector_registry=HOURLY_COLLECTORS,
        collection_mode="hourly",
        timestamp=start_datetime,
        db_connection=db_connection,
        collector_kwargs={"since": start_datetime, "until": end_datetime},
    )
