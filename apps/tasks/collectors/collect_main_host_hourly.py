"""
Collect main_host metrics hourly and store in HourlyMetricsCollection.

This task collects main_host data for a specific hour and stores it
in the database for later aggregation and anonymization.
"""

import logging
from typing import Any

from ..utils import task, task_execution_wrapper
from .helpers import _collect_hourly_metrics, main_host

logger = logging.getLogger(__name__)


@task(queue="metrics_collectors", decorate=False)
@task_execution_wrapper("collect_main_host_hourly")
def collect_main_host_hourly(**kwargs) -> dict[str, Any]:
    """
    Collect main_host metrics hourly and store in HourlyMetricsCollection.

    Args:
        **kwargs: Task data containing:
            - hour_timestamp (str): ISO timestamp for the hour to collect (optional)
            - database (str): Database name (default: 'awx')

    Returns:
        dict: Task result with collection status and record ID
    """
    return _collect_hourly_metrics(
        collector_name="main_host",
        collector_func=main_host,
        task_name="collect_main_host_hourly",
        uses_date_range=False,
        **kwargs,
    )
