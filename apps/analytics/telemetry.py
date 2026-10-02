"""Prometheus instrumentation for analytics collector reads."""

from __future__ import annotations

import logging
import os
from typing import Any

from prometheus_client import CollectorRegistry, Counter, Histogram, generate_latest, multiprocess
from prometheus_client.parser import text_string_to_metric_families

from apps.analytics.registry import get_entry

logger = logging.getLogger(__name__)

ANALYTICS_REQUESTS = Counter(
    "analytics_collector_get_requests_total",
    "Total GET requests to enabled analytics collectors.",
    ["collector"],
)
ANALYTICS_REQUEST_DURATION = Histogram(
    "analytics_collector_get_duration_milliseconds",
    "Duration of enabled analytics collector GET requests in milliseconds.",
    ["collector"],
    buckets=(1, 5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000, 10000, float("inf")),
)

_REQUESTS_SAMPLE = "analytics_collector_get_requests_total"
_DURATION_COUNT_SAMPLE = "analytics_collector_get_duration_milliseconds_count"
_DURATION_SUM_SAMPLE = "analytics_collector_get_duration_milliseconds_sum"


def record_collector_get(collector: str, duration_ms: float) -> None:
    """Record one enabled collector GET without affecting the API response."""
    entry = get_entry(collector)
    if entry is None or not entry.enabled or entry.name != collector:
        return

    try:
        ANALYTICS_REQUESTS.labels(collector=entry.name).inc()
        ANALYTICS_REQUEST_DURATION.labels(collector=entry.name).observe(max(duration_ms, 0))
    except Exception:
        logger.exception("Failed to record analytics telemetry for %s", entry.name)


def _metrics_registry() -> CollectorRegistry:
    """Return the same registry shape used by the existing Prometheus endpoint."""
    if "PROMETHEUS_MULTIPROC_DIR" in os.environ or "prometheus_multiproc_dir" in os.environ:
        registry = CollectorRegistry()
        multiprocess.MultiProcessCollector(registry)
        return registry
    from prometheus_client import REGISTRY

    return REGISTRY


def _valid_collector(labels: dict[str, str]) -> str | None:
    """Return a canonical enabled collector label, rejecting unexpected labels."""
    if set(labels) != {"collector"}:
        return None
    collector = labels["collector"]
    entry = get_entry(collector)
    if entry is None or not entry.enabled or entry.name != collector:
        return None
    return collector


def aggregate_analytics_usage() -> dict[str, dict[str, Any]]:
    """Read Prometheus aggregates and calculate per-collector usage statistics.

    The values are cumulative since the process metrics were initialized (or since the
    Prometheus multiprocess files were reset). The Prometheus scrape combines worker
    processes before this function derives the average from duration sum/count.
    """
    try:
        families = text_string_to_metric_families(generate_latest(_metrics_registry()).decode("utf-8"))
        usage: dict[str, dict[str, Any]] = {}
        for family in families:
            for sample in family.samples:
                collector = _valid_collector(sample.labels)
                if collector is None:
                    continue
                values = usage.setdefault(collector, {})
                if sample.name == _REQUESTS_SAMPLE:
                    values["request_count"] = int(sample.value)
                elif sample.name == _DURATION_SUM_SAMPLE:
                    values["duration_ms_total"] = float(sample.value)
                elif sample.name == _DURATION_COUNT_SAMPLE:
                    values["duration_sample_count"] = int(sample.value)

        for values in usage.values():
            duration_count = values.get("duration_sample_count", 0)
            duration_total = values.get("duration_ms_total", 0.0)
            values["duration_ms_average"] = duration_total / duration_count if duration_count else None
            values.pop("duration_sample_count", None)
        return usage
    except Exception:
        logger.exception("Failed to aggregate analytics Prometheus telemetry")
        return {}
