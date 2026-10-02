"""Collect Prometheus aggregates for analytics API usage telemetry."""

from __future__ import annotations

from typing import Any

from apps.analytics.telemetry import aggregate_analytics_usage
from apps.tasks.utils import create_task_result


def collect_analytics_usage(**kwargs) -> dict[str, Any]:
    """Return the current aggregate analytics usage without customer data."""
    del kwargs
    return create_task_result("success", {"analytics_usage": aggregate_analytics_usage()})
