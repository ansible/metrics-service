"""
Collect unified_jobs metrics hourly and compute rollup statistics.
"""

import logging
from typing import Any

from ..utils import task, task_execution_wrapper
from .helpers import _collect_hourly_metrics

logger = logging.getLogger(__name__)


@task(queue="metrics_collectors", decorate=False)
@task_execution_wrapper("collect_unified_jobs_hourly")
def collect_unified_jobs_hourly(**kwargs) -> dict[str, Any]:
    """
    Collect unified_jobs metrics hourly (MAP phase).

    Collects raw unified_jobs data from AWX database for a specific hour,
    computes rollup statistics using JobsAnonymizedRollup, and stores
    in HourlyMetricsCollection.
    """
    from metrics_utility.anonymized_rollups.jobs_anonymized_rollup import (
        JobsAnonymizedRollup as JobsRollupProcessor,
    )
    from metrics_utility.library.collectors.controller import unified_jobs

    return _collect_hourly_metrics(
        collector_name="unified_jobs",
        collector_func=unified_jobs,
        rollup_processor=JobsRollupProcessor(),
        task_name="collect_unified_jobs_hourly",
        uses_date_range=True,
        **kwargs,
    )
