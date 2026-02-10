"""
Collect job host summary metrics hourly and store in HourlyMetricsCollection.

This task collects job_host_summary data for a specific hour and stores it
in the database for later aggregation and anonymization.
"""

import logging
from typing import Any

from ..utils import task, task_execution_wrapper
from .helpers import _collect_hourly_metrics, job_host_summary

logger = logging.getLogger(__name__)


@task(queue="metrics_collectors", decorate=False)
@task_execution_wrapper("collect_job_host_summary_hourly")
def collect_job_host_summary_hourly(**kwargs) -> dict[str, Any]:
    """
    Collect job host summary metrics hourly and store in HourlyMetricsCollection.

    Args:
        **kwargs: Task data containing:
            - hour_timestamp (str): ISO timestamp for the hour to collect (optional)
            - database (str): Database name (default: 'awx')

    Returns:
        dict: Task result with collection status and record ID
    """
    return _collect_hourly_metrics(
        collector_name="job_host_summary",
        collector_func=job_host_summary,
        task_name="collect_job_host_summary_hourly",
        uses_date_range=True,
        **kwargs,
    )
