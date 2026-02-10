"""
Collect host metrics (main_jobevent) hourly and store in HourlyMetricsCollection.

This task collects main_jobevent data for a specific hour and stores it
in the database for later aggregation and anonymization.
"""

import logging
from typing import Any

from ..utils import task, task_execution_wrapper
from .helpers import _collect_hourly_metrics, main_jobevent

logger = logging.getLogger(__name__)


@task(queue="metrics_collectors", decorate=False)
@task_execution_wrapper("collect_host_metrics_hourly")
def collect_host_metrics_hourly(**kwargs) -> dict[str, Any]:
    """
    Collect host metrics (main_jobevent) hourly and store in HourlyMetricsCollection.

    Args:
        **kwargs: Task data containing:
            - hour_timestamp (str): ISO timestamp for the hour to collect (optional)
            - database (str): Database name (default: 'awx')

    Returns:
        dict: Task result with collection status and record ID
    """
    return _collect_hourly_metrics(
        collector_name="main_jobevent",
        collector_func=main_jobevent,
        task_name="collect_host_metrics_hourly",
        uses_date_range=True,
        **kwargs,
    )
