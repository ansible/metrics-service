"""
Generic metrics collector that handles all collector types via configuration.

This module provides a single collector function that can handle any metrics
collector type by using a registry-based approach. This eliminates code
duplication across multiple collector files.
"""

import importlib
import logging
from typing import Any

from ..utils import task, task_execution_wrapper
from .helpers import _collect_hourly_metrics

logger = logging.getLogger(__name__)


# Registry mapping collector_type to configuration
COLLECTOR_REGISTRY = {
    "job_host_summary_service": {
        "collector_module": "metrics_utility.library.collectors.controller",
        "collector_func": "job_host_summary_service",
        "rollup_module": "metrics_utility.anonymized_rollups.jobhostsummary_anonymized_rollup",
        "rollup_class": "JobHostSummaryAnonymizedRollup",
        "uses_date_range": True,
        "description": "Job host summary metrics (partition-optimized)",
    },
    "unified_jobs": {
        "collector_module": "metrics_utility.library.collectors.controller",
        "collector_func": "unified_jobs",
        "rollup_module": "metrics_utility.anonymized_rollups.jobs_anonymized_rollup",
        "rollup_class": "JobsAnonymizedRollup",
        "uses_date_range": True,
        "description": "Unified jobs metrics",
    },
    "credentials_service": {
        "collector_module": "metrics_utility.library.collectors.controller",
        "collector_func": "credentials_service",
        "rollup_module": "metrics_utility.anonymized_rollups.credentials_anonymized_rollup",
        "rollup_class": "CredentialsAnonymizedRollup",
        "uses_date_range": True,
        "description": "Credentials usage metrics",
    },
    "job_events": {
        "collector_module": "metrics_utility.library.collectors.controller",
        "collector_func": "main_jobevent",
        "rollup_module": "metrics_utility.anonymized_rollups.events_modules_anonymized_rollup",
        "rollup_class": "EventModulesAnonymizedRollup",
        "uses_date_range": True,
        "description": "Job events (event modules) metrics",
    },
    "execution_environments": {
        "collector_module": "metrics_utility.library.collectors.controller",
        "collector_func": "execution_environments",
        "rollup_module": "metrics_utility.anonymized_rollups.execution_environments_anonymized_rollup",
        "rollup_class": "ExecutionEnvironmentsAnonymizedRollup",
        "uses_date_range": False,  # Snapshot collector, no time range
        "description": "Execution environments snapshot",
    },
}


@task(queue="metrics_collectors", decorate=False)
@task_execution_wrapper("collect_metrics_generic")
def collect_metrics_generic(**kwargs) -> dict[str, Any]:
    """
    Generic metrics collector that handles all collector types.

    The collector type is determined by the 'collector_type' parameter,
    which must match a key in COLLECTOR_REGISTRY.

    This function dynamically imports the appropriate collector function
    and rollup processor based on the collector_type, then delegates to
    the shared _collect_hourly_metrics helper.

    Args:
        **kwargs: Task data containing:
            - collector_type (str): Type of collector (required)
            - hour_timestamp (str): ISO timestamp for the hour to collect (optional)
            - database (str): Database name (default: 'awx')

    Returns:
        dict: Task result with collection status and record ID

    Raises:
        ValueError: If collector_type is missing or not in registry
        ImportError: If collector modules cannot be imported
    """
    collector_type = kwargs.pop("collector_type", None)
    if not collector_type:
        raise ValueError("collector_type parameter is required")

    if collector_type not in COLLECTOR_REGISTRY:
        valid_types = ", ".join(sorted(COLLECTOR_REGISTRY.keys()))
        raise ValueError(f"Unknown collector_type: {collector_type}. Valid types: {valid_types}")

    config = COLLECTOR_REGISTRY[collector_type]

    logger.info(f"Collecting metrics for collector_type: {collector_type} ({config['description']})")

    # Dynamically import collector function
    collector_module = importlib.import_module(config["collector_module"])
    collector_func = getattr(collector_module, config["collector_func"])

    # Dynamically import and instantiate rollup processor
    rollup_module = importlib.import_module(config["rollup_module"])
    rollup_class = getattr(rollup_module, config["rollup_class"])
    rollup_processor = rollup_class()

    return _collect_hourly_metrics(
        collector_name=collector_type,
        collector_func=collector_func,
        rollup_processor=rollup_processor,
        task_name=f"collect_{collector_type}",
        uses_date_range=config["uses_date_range"],
        **kwargs,
    )
