"""
Collect job host summary metrics hourly and compute rollup statistics.

This task collects job_host_summary_service data (partition-optimized variant)
for a specific hour and immediately computes rollup statistics (MAP phase).
Only the aggregated rollup is stored, not the raw rows, to save database space.
"""

import logging
from typing import Any

from ..utils import task, task_execution_wrapper
from .helpers import _collect_hourly_metrics

logger = logging.getLogger(__name__)


@task(queue="metrics_collectors", decorate=False)
@task_execution_wrapper("collect_job_host_summary_hourly")
def collect_job_host_summary_hourly(**kwargs) -> dict[str, Any]:
    """
    Collect job host summary metrics hourly and compute rollup statistics (MAP phase).

    This task:
    1. Collects raw job_host_summary_service CSV data from AWX database (partition-optimized)
    2. Computes rollup statistics immediately using JobHostSummaryRollupProcessor
    3. Stores only the rollup statistics in HourlyMetricsCollection

    Args:
        **kwargs: Task data containing:
            - hour_timestamp (str): ISO timestamp for the hour to collect (optional)
            - database (str): Database name (default: 'awx')

    Returns:
        dict: Task result with collection status and record ID
    """
    # Import from metrics-utility (will fail if not available)
    from metrics_utility.anonymized_rollups.jobhostsummary_anonymized_rollup import (
        JobHostSummaryAnonymizedRollup as JobHostSummaryRollupProcessor,
    )
    from metrics_utility.library.collectors.controller import job_host_summary_service

    return _collect_hourly_metrics(
        collector_name="job_host_summary_service",
        collector_func=job_host_summary_service,
        rollup_processor=JobHostSummaryRollupProcessor(),
        task_name="collect_job_host_summary_hourly",
        uses_date_range=True,
        **kwargs,
    )
