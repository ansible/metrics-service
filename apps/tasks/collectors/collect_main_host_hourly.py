"""
Collect main_host metrics daily (snapshot data).

NOTE: main_host is a snapshot collector that doesn't support time ranges.
It should be collected once per day, not hourly. This task is scheduled
hourly for consistency but only the latest snapshot is used in daily rollups.

This task collects main_host data and stores it in HourlyMetricsCollection.
"""

import logging
from typing import Any

from ..utils import task, task_execution_wrapper
from .helpers import _collect_hourly_metrics

logger = logging.getLogger(__name__)


@task(queue="metrics_collectors", decorate=False)
@task_execution_wrapper("collect_main_host_hourly")
def collect_main_host_hourly(**kwargs) -> dict[str, Any]:
    """
    Collect main_host snapshot data.

    NOTE: main_host is a snapshot collector (no since/until support).
    Consider moving this to daily collection instead of hourly.

    Args:
        **kwargs: Task data containing:
            - hour_timestamp (str): ISO timestamp for the collection (optional)
            - database (str): Database name (default: 'awx')

    Returns:
        dict: Task result with collection status and record ID
    """
    # Import from metrics-utility (will fail if not available)
    from metrics_utility.library.collectors.controller import main_host

    # main_host has no rollup processor - it's stored as-is
    # This is a simple snapshot, not aggregated data
    # TODO: Move to daily collection or use latest snapshot only
    return _collect_hourly_metrics(
        collector_name="main_host",
        collector_func=main_host,
        rollup_processor=None,  # No rollup needed for snapshot data
        task_name="collect_main_host_hourly",
        uses_date_range=False,
        **kwargs,
    )
