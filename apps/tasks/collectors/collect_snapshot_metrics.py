"""
Snapshot metrics collector for point-in-time data.

Collects current state snapshots (not time-series), computes rollup
statistics, and stores in HourlyMetricsCollection.
"""

import logging
from typing import Any

from django.utils import timezone
from metrics_utility.anonymized_rollups.execution_environments_anonymized_rollup import (
    ExecutionEnvironmentsAnonymizedRollup,
)
from metrics_utility.library.collectors.controller import (
    config,
    execution_environments,
)

from ..utils import create_task_result, get_db_connection, log_task_execution, task, task_execution_wrapper

logger = logging.getLogger(__name__)

# Registry mapping collector_type to (collector_func, rollup_processor_class)
# rollup_processor can be None for collectors that don't need processing (e.g., config)
SNAPSHOT_COLLECTORS = {
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
    from apps.tasks.models import HourlyMetricsCollection

    collector_type = kwargs.pop("collector_type", None)
    if not collector_type:
        raise ValueError("collector_type parameter is required")

    if collector_type not in SNAPSHOT_COLLECTORS:
        valid_types = ", ".join(sorted(SNAPSHOT_COLLECTORS.keys()))
        raise ValueError(f"Unknown collector_type: {collector_type}. Valid types: {valid_types}")

    config = SNAPSHOT_COLLECTORS[collector_type]
    collector_func = config["collector_func"]
    rollup_processor_class = config["rollup_processor"]

    snapshot_timestamp = timezone.now()

    log_task_execution(
        f"collect_{collector_type}",
        "processing",
        f"Collecting {collector_type} snapshot at: {snapshot_timestamp}",
    )

    try:
        # Get database connection
        db_connection = get_db_connection()

        # Collect snapshot data from AWX database (no time range)
        collector = collector_func(db=db_connection)
        raw_data = collector.gather()

        # Compute rollup statistics if processor is defined
        if rollup_processor_class is not None:
            rollup_processor = rollup_processor_class()
            rollup_result = rollup_processor.prepare_base(raw_data)

            # Extract rollup data from result
            # The rollup_result structure varies by processor but typically has 'json' and 'rollup' keys
            if isinstance(rollup_result, dict):
                rollup_data = rollup_result.get("json") or rollup_result.get("rollup") or rollup_result
            else:
                rollup_data = rollup_result
        else:
            # No rollup processor - use raw data as-is (e.g., config)
            rollup_data = raw_data

        # Use the current hour timestamp for snapshot collections
        # (HourlyMetricsCollection expects a timestamp even for snapshots)
        collection_timestamp = snapshot_timestamp.replace(minute=0, second=0, microsecond=0)

        # Create or update HourlyMetricsCollection record
        collection, created = HourlyMetricsCollection.objects.update_or_create(
            collector_type=collector_type,
            collection_timestamp=collection_timestamp,
            defaults={
                "raw_data": rollup_data,
                "collection_completed_at": timezone.now(),
            },
        )

        action = "Created" if created else "Updated"
        log_task_execution(
            f"collect_{collector_type}",
            "completed",
            f"{action} snapshot collection ID: {collection.id} at {snapshot_timestamp}",
        )

        return create_task_result(
            "success",
            {
                "message": f"{action} snapshot collection for {collector_type}",
                "task_type": f"collect_{collector_type}",
                "collection_id": collection.id,
                "collector_type": collector_type,
                "snapshot_timestamp": snapshot_timestamp.isoformat(),
            },
        )

    except Exception as e:
        logger.exception(f"Failed to collect {collector_type} snapshot metrics: {str(e)}")
        return create_task_result(
            "error",
            {
                "task_type": f"collect_{collector_type}",
                "collector_type": collector_type,
            },
            error=f"Collection failed: {str(e)}",
        )
