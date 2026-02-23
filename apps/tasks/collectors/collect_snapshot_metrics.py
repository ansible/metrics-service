"""
Snapshot metrics collector for point-in-time data.

Collects current state snapshots (not time-series), computes rollup
statistics, and stores in HourlyMetricsCollection.
"""

import logging
from datetime import datetime, timedelta
from typing import Any

from django.utils import timezone

from ..utils import generic_collect_metrics, get_db_connection, task, task_execution_wrapper

logger = logging.getLogger(__name__)


def _get_snapshot_collectors():
    """
    Get snapshot collectors registry with lazy imports.

    Lazy imports prevent metrics_utility dependency from breaking
    unrelated task registration (e.g., hello_world, cleanup_old_tasks).
    """
    from metrics_utility.anonymized_rollups import (
        ControllerVersionAnonymizedRollup,
        ExecutionEnvironmentsAnonymizedRollup,
        TableMetadataAnonymizedRollup,
    )
    from metrics_utility.library.collectors.controller import (
        config,
        controller_version_service,
        execution_environments,
        table_metadata,
    )

    # Registry mapping collector_type to (collector_func, rollup_processor_class)
    # rollup_processor can be None for collectors that don't need processing (e.g., config)
    return {
        "execution_environments": {
            "collector_func": execution_environments,
            "rollup_processor": ExecutionEnvironmentsAnonymizedRollup,
            "description": "Execution environments snapshot",
        },
        "config": {
            "collector_func": config,
            "rollup_processor": None,  # Config is raw data, no rollup processing needed
            "description": "System configuration snapshot",
        },
        "controller_version_service": {
            "collector_func": controller_version_service,
            "rollup_processor": ControllerVersionAnonymizedRollup,
            "description": "Controller version snapshot",
        },
        "table_metadata": {
            "collector_func": table_metadata,
            "rollup_processor": TableMetadataAnonymizedRollup,
            "description": "Table metadata snapshot",
        },
    }


@task(queue="metrics_collectors", decorate=False)
@task_execution_wrapper("collect_snapshot_metrics")
def collect_snapshot_metrics(**kwargs) -> dict[str, Any]:
    """
    Collect snapshot metrics for a specific collector type.

    This function handles all snapshot collectors that gather current
    state data (not time-series). It collects raw data, computes rollup
    statistics, and stores only the rollup in HourlyMetricsCollection.

    Args:
        **kwargs: Task data containing:
            - collector_type (str): Type of collector (required)
            - database (str): Database name (default: 'awx')

    Returns:
        dict: Task result with collection status and record ID

    Raises:
        ValueError: If collector_type is missing or invalid
    """
    collector_type = kwargs.pop("collector_type", None)
    if not collector_type:
        raise ValueError("collector_type parameter is required")

    # Extract optional execution_id for linking to TaskExecution
    execution_id = kwargs.get("execution_id")  # Available when called via execute_db_task

    snapshot_timestamp = timezone.now()

    # FIXME: temporary fix, but this needs more intentionality
    # Snapshot collections belong to the previous day (the day being summarized)
    # Use 23:00 of the previous day to ensure they fall within the daily rollup's query window
    # which is [midnight previous_day, midnight today). This prevents snapshots from falling
    # outside the rollup query when they run after midnight.
    previous_day = snapshot_timestamp.date() - timedelta(days=1)
    collection_timestamp = timezone.make_aware(datetime.combine(previous_day, datetime.min.time())).replace(
        hour=23, minute=0, second=0, microsecond=0
    )

    # Get database connection
    db_connection = get_db_connection()

    # For auditing, store collection date at start of day (not the 23:00 trick used for rollup query)
    # This makes auditing clearer - snapshots represent "state at end of this day"
    collection_date = collection_timestamp.replace(hour=0, minute=0, second=0, microsecond=0)

    # Use generic collector without time window (snapshot = current state)
    # Pass collection_time in collector_kwargs for audit - it gets filtered out before calling collector
    return generic_collect_metrics(
        collector_type=collector_type,
        collector_registry=_get_snapshot_collectors(),
        collection_mode="snapshot",
        timestamp=collection_timestamp,
        db_connection=db_connection,
        collector_kwargs={"collection_time": collection_date},
        task_execution_id=execution_id,
    )
