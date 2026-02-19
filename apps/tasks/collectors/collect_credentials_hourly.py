"""
Collect credentials metrics hourly and compute rollup statistics.
"""

import logging
from typing import Any

from ..utils import task, task_execution_wrapper
from .helpers import _collect_hourly_metrics

logger = logging.getLogger(__name__)


@task(queue="metrics_collectors", decorate=False)
@task_execution_wrapper("collect_credentials_hourly")
def collect_credentials_hourly(**kwargs) -> dict[str, Any]:
    """
    Collect credentials metrics hourly (MAP phase).

    Collects raw credentials_service data from AWX database for a specific hour,
    computes rollup statistics using CredentialsAnonymizedRollup, and stores
    in HourlyMetricsCollection.
    """
    from metrics_utility.anonymized_rollups.credentials_anonymized_rollup import (
        CredentialsAnonymizedRollup as CredentialsRollupProcessor,
    )
    from metrics_utility.library.collectors.controller import credentials_service

    return _collect_hourly_metrics(
        collector_name="credentials_service",
        collector_func=credentials_service,
        rollup_processor=CredentialsRollupProcessor(),
        task_name="collect_credentials_hourly",
        uses_date_range=True,
        **kwargs,
    )
