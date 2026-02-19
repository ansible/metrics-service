"""
Collect execution_environments snapshot data daily.
"""

import logging
from typing import Any

from ..utils import task, task_execution_wrapper
from .helpers import _collect_hourly_metrics  # Reusable for daily too

logger = logging.getLogger(__name__)


@task(queue="metrics_collectors", decorate=False)
@task_execution_wrapper("collect_execution_environments_daily")
def collect_execution_environments_daily(**kwargs) -> dict[str, Any]:
    """
    Collect execution_environments snapshot daily.

    Collects execution_environments snapshot from AWX database,
    computes rollup statistics using ExecutionEnvironmentsAnonymizedRollup,
    and stores in HourlyMetricsCollection (despite name, used for daily snapshots too).
    """
    from metrics_utility.anonymized_rollups.execution_environments_anonymized_rollup import (
        ExecutionEnvironmentsAnonymizedRollup as ExecutionEnvironmentsRollupProcessor,
    )
    from metrics_utility.library.collectors.controller import execution_environments

    return _collect_hourly_metrics(
        collector_name="execution_environments",
        collector_func=execution_environments,
        rollup_processor=ExecutionEnvironmentsRollupProcessor(),
        task_name="collect_execution_environments_daily",
        uses_date_range=False,  # Snapshot collector, no time range
        **kwargs,
    )
