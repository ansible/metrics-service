"""
Snapshot metrics collector for point-in-time data.

Collects current state snapshots (not time-series), computes rollup
statistics, and stores in HourlyMetricsCollection.
"""

import logging
from typing import Any

from django.utils import timezone
from metrics_utility.anonymized_rollups import ExecutionEnvironmentsAnonymizedRollup
from metrics_utility.library.collectors.controller import config, execution_environments

from ..utils import generic_collect_metrics, get_db_connection, task, task_execution_wrapper

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
    collector_type = kwargs.pop("collector_type", None)
    if not collector_type:
        raise ValueError("collector_type parameter is required")

    snapshot_timestamp = timezone.now()

    # Use the current hour timestamp for snapshot collections
    # (HourlyMetricsCollection expects a timestamp even for snapshots)
    collection_timestamp = snapshot_timestamp.replace(minute=0, second=0, microsecond=0)

    # Get database connection
    db_connection = get_db_connection()

    # Use generic collector without time window (snapshot = current state)
    return generic_collect_metrics(
        collector_type=collector_type,
        collector_registry=SNAPSHOT_COLLECTORS,
        collection_mode="snapshot",
        timestamp=collection_timestamp,
        db_connection=db_connection,
        collector_kwargs={},  # No time range for snapshots
    )
