"""Prometheus instrumentation and daily usage aggregation for analytics collector reads."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from ansible_base.resource_registry.resource_server import get_service_token
from django.conf import settings
from prometheus_client import Counter, Histogram
from prometheus_client.parser import text_string_to_metric_families

from apps.analytics.registry import CollectorEntry, get_entry

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
_ZERO_METRICS = {"request_count": 0, "duration_ms_total": 0.0, "duration_sample_count": 0}

# The token only has to survive one in-cluster request, but it is minted before the socket is
# opened, so it must cover the connect and read timeouts with room to spare.
_TOKEN_TTL_SECONDS = 60


def _service_token() -> str:
    """Mint a short-lived service token with an explicitly UTC-based expiry.

    ``get_service_token(expiration=...)`` builds ``exp`` from a naive ``datetime.now()``, which
    PyJWT then encodes as if it were UTC. On a container whose ``TZ`` is behind UTC that yields a
    token that is already expired; ahead of UTC it silently outlives its intended lifetime. Passing
    ``exp`` ourselves as a UTC timestamp keeps the lifetime correct regardless of the local zone.
    """
    exp = datetime.now(UTC) + timedelta(seconds=_TOKEN_TTL_SECONDS)
    return get_service_token(expiration=None, exp=int(exp.timestamp()))


class _NoRedirectHandler(HTTPRedirectHandler):
    """Do not forward the internal service token to a redirected host."""

    def redirect_request(self, request, file_pointer, code, message, headers, new_url):
        return None


def _open_metrics_endpoint(request: Request, timeout: int):
    """Make a direct in-cluster request without proxy or redirect handling."""
    opener = build_opener(ProxyHandler({}), _NoRedirectHandler())
    return opener.open(request, timeout=timeout)  # noqa: S310 - endpoint URL is validated and config-controlled


def record_collector_get(entry: CollectorEntry, duration_ms: float) -> None:
    """Record one enabled collector GET without affecting the API response."""
    if not entry.enabled:
        return

    try:
        ANALYTICS_REQUESTS.labels(collector=entry.name).inc()
        ANALYTICS_REQUEST_DURATION.labels(collector=entry.name).observe(max(duration_ms, 0))
    except Exception:
        logger.exception("Failed to record analytics telemetry for %s", entry.name)


def _registry_collector(labels: dict[str, str]) -> CollectorEntry | None:
    """Return a known canonical collector label, rejecting unexpected labels."""
    if set(labels) != {"collector"}:
        return None
    collector = labels["collector"]
    entry = get_entry(collector)
    if entry is None or entry.name != collector:
        return None
    return entry


def aggregate_analytics_usage() -> dict[str, dict[str, Any]] | None:
    """Scrape the local web Service's Prometheus endpoint for cumulative usage.

    The metrics endpoint uses ``MultiProcessCollector`` in the web pod, so its
    response includes all Gunicorn workers sharing that pod's multiprocess
    directory. A failed scrape returns ``None``; a successful scrape with no
    analytics samples returns an empty mapping.
    """
    metrics_url = settings.INTERNAL_PROMETHEUS_URL
    if not metrics_url:
        logger.error("INTERNAL_PROMETHEUS_URL is not configured; skipping analytics usage scrape")
        return None
    try:
        parsed_url = urlsplit(metrics_url)
        if (
            parsed_url.scheme not in {"http", "https"}
            or not parsed_url.hostname
            or parsed_url.username
            or parsed_url.password
        ):
            raise ValueError("INTERNAL_PROMETHEUS_URL must be an HTTP(S) URL with a hostname and no user info")

        request = Request(  # noqa: S310 - metrics_url is deployment-controlled and HTTP(S)-validated above
            metrics_url,
            headers={"X-ANSIBLE-SERVICE-AUTH": _service_token()},
        )
        # This deployment-controlled URL targets the in-cluster web Service; reject non-HTTP schemes above.
        with _open_metrics_endpoint(request, timeout=settings.INTERNAL_PROMETHEUS_TIMEOUT) as response:
            exposition = response.read().decode("utf-8")

        metrics: dict[str, dict[str, Any]] = {}
        for family in text_string_to_metric_families(exposition):
            for sample in family.samples:
                entry = _registry_collector(sample.labels)
                if entry is None:
                    continue

                values = metrics.setdefault(entry.name, {})
                if sample.name == _REQUESTS_SAMPLE:
                    values["request_count"] = int(sample.value)
                elif sample.name == _DURATION_SUM_SAMPLE:
                    values["duration_ms_total"] = float(sample.value)
                elif sample.name == _DURATION_COUNT_SAMPLE:
                    values["duration_sample_count"] = int(sample.value)

        for values in metrics.values():
            for name, default in _ZERO_METRICS.items():
                values.setdefault(name, default)
        return metrics
    except (HTTPError, URLError, OSError, ValueError):
        logger.exception("Failed to scrape analytics Prometheus endpoint %s", metrics_url)
        return None
    except Exception:
        # Metrics collection must never make the normal rollup fail.
        logger.exception("Failed to aggregate analytics Prometheus telemetry")
        return None


def daily_analytics_usage_delta(
    current: dict[str, dict[str, Any]],
    previous_snapshot: dict[str, Any] | None,
) -> dict[str, dict[str, Any]]:
    """Calculate usage since the previous successful scrape.

    The first successful scrape establishes the baseline and intentionally
    produces no daily values. If a counter is lower than its previous value,
    the multiprocess files were reset; use the current value as the best
    available post-reset delta and log the reset.
    """
    if not previous_snapshot or "metrics" not in previous_snapshot:
        return {}

    previous = previous_snapshot["metrics"]
    usage: dict[str, dict[str, Any]] = {}
    for collector, previous_values in previous.items():
        if collector not in current and any(previous_values.get(name, 0) for name in _ZERO_METRICS):
            logger.warning("Prometheus counters disappeared for analytics collector %s", collector)

    for collector, current_values in current.items():
        entry = get_entry(collector)
        if entry is None or not entry.enabled or entry.name != collector:
            continue

        previous_values = previous.get(collector, _ZERO_METRICS)
        names = ("request_count", "duration_ms_total", "duration_sample_count")
        reset = any(current_values.get(name, 0) < previous_values.get(name, 0) for name in names)
        if reset:
            logger.warning("Prometheus counters reset for analytics collector %s; using current values", collector)

        deltas = {
            name: current_values.get(name, 0) if reset else current_values.get(name, 0) - previous_values.get(name, 0)
            for name in names
        }
        usage[collector] = {
            "request_count": int(deltas["request_count"]),
            "duration_ms_total": float(deltas["duration_ms_total"]),
            "duration_ms_average": (
                float(deltas["duration_ms_total"]) / int(deltas["duration_sample_count"])
                if deltas["duration_sample_count"]
                else None
            ),
        }
    return usage
