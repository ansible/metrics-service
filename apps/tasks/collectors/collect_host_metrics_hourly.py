"""
Collect host metrics (main_jobevent) hourly and compute rollup statistics.

This task collects main_jobevent data for a specific hour and immediately
computes rollup statistics (MAP phase). Only the aggregated rollup is stored,
not the raw rows, to save database space.
"""

import logging
from typing import Any

from ..utils import task, task_execution_wrapper
from .helpers import _collect_hourly_metrics

logger = logging.getLogger(__name__)


@task(queue="metrics_collectors", decorate=False)
@task_execution_wrapper("collect_host_metrics_hourly")
def collect_host_metrics_hourly(**kwargs) -> dict[str, Any]:
    """
    Collect host metrics (main_jobevent) hourly and compute rollup statistics (MAP phase).

    This task:
    1. Collects raw main_jobevent CSV data from AWX database
    2. Computes rollup statistics immediately using EventModulesRollupProcessor
    3. Stores only the rollup statistics in HourlyMetricsCollection

    Args:
        **kwargs: Task data containing:
            - hour_timestamp (str): ISO timestamp for the hour to collect (optional)
            - database (str): Database name (default: 'awx')

    Returns:
        dict: Task result with collection status and record ID
    """
    # Import from metrics-utility (will fail if not available)
    from metrics_utility.anonymized_rollups.events_modules_anonymized_rollup import (
        EventModulesAnonymizedRollup as EventModulesRollupProcessor,
    )
    from metrics_utility.library.collectors.controller import main_jobevent

    return _collect_hourly_metrics(
        collector_name="main_jobevent",
        collector_func=main_jobevent,
        rollup_processor=EventModulesRollupProcessor(),
        task_name="collect_host_metrics_hourly",
        uses_date_range=True,
        **kwargs,
    )
