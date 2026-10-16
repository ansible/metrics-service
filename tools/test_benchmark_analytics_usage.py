"""Opt-in benchmark for the analytics GET usage write overhead.

Run against pytest's isolated PostgreSQL test database with:

    METRICS_SERVICE_MODE=test uv run pytest -s tools/test_benchmark_analytics_usage.py

All generated payload and usage rows are rolled back with the test transaction.
"""

from __future__ import annotations

import statistics
import time
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.conf import settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.analytics.models import AnalyticsPayload, AnalyticsUsage

COLLECTOR = "controller.config"
URL = f"/api/v1/analytics/{COLLECTOR}/?page_size=5"
PAYLOAD_ROW_COUNTS = (0, 10_000)
WARMUP_REQUESTS = 10
MEASURED_REQUESTS = 100
COLD_INSERT_REQUESTS = 25


def _request_duration_ms(client: APIClient, *, instrumented: bool) -> float:
    """Time one collector GET through Django's test client and assert it succeeded."""
    start = time.perf_counter_ns()
    if instrumented:
        response = client.get(URL)
    else:
        with patch("apps.analytics.v1.views.record_collector_get"):
            response = client.get(URL)
    elapsed_ms = (time.perf_counter_ns() - start) / 1_000_000
    assert response.status_code == 200
    return elapsed_ms


def _percentile(samples: list[float], fraction: float) -> float:
    """Return a nearest-rank percentile for the measured request durations."""
    ordered = sorted(samples)
    return ordered[max(0, int(len(ordered) * fraction + 0.999999) - 1)]


def _populate_payloads(row_count: int) -> None:
    """Create deterministic collector rows for the populated-data scenario."""
    AnalyticsPayload.objects.filter(collector=COLLECTOR).delete()
    if not row_count:
        return

    started_at = timezone.now() - timedelta(days=1)
    AnalyticsPayload.objects.bulk_create(
        [
            AnalyticsPayload(
                collector=COLLECTOR,
                started_at=started_at + timedelta(seconds=index),
                finished_at=started_at + timedelta(seconds=index + 1),
                payload={"benchmark_row": index},
            )
            for index in range(row_count)
        ],
        batch_size=1000,
    )


@pytest.mark.django_db
def test_benchmark_analytics_get_overhead():
    """Print baseline and instrumented latency for empty and large payload tables."""
    assert settings.TESTING, "Run this benchmark with METRICS_SERVICE_MODE=test"
    client = APIClient()
    usage_date = timezone.now().date()

    # Permission evaluation is held constant and excluded; this isolates the GET + telemetry write.
    with patch("apps.analytics.v1.views.CollectorRowsView.permission_classes", []):
        for payload_rows in PAYLOAD_ROW_COUNTS:
            _populate_payloads(payload_rows)
            AnalyticsUsage.objects.filter(usage_date=usage_date, collector=COLLECTOR).delete()

            for _ in range(WARMUP_REQUESTS):
                _request_duration_ms(client, instrumented=False)

            # Measure inserts separately from steady-state increments. Deletion is outside the
            # timed request and all writes roll back with the test transaction.
            cold_insert_samples = []
            for _ in range(COLD_INSERT_REQUESTS):
                AnalyticsUsage.objects.filter(usage_date=usage_date, collector=COLLECTOR).delete()
                cold_insert_samples.append(_request_duration_ms(client, instrumented=True))

            uninstrumented: list[float] = []
            instrumented: list[float] = []
            for index in range(MEASURED_REQUESTS):
                order = (False, True) if index % 2 == 0 else (True, False)
                for is_instrumented in order:
                    elapsed = _request_duration_ms(client, instrumented=is_instrumented)
                    (instrumented if is_instrumented else uninstrumented).append(elapsed)

            baseline_median = statistics.median(uninstrumented)
            instrumented_median = statistics.median(instrumented)
            print(  # noqa: T201 - benchmark results are the test's output
                f"payload_rows={payload_rows} warm_median_ms: "
                f"uninstrumented={baseline_median:.3f}, "
                f"instrumented={instrumented_median:.3f}, "
                f"delta={instrumented_median - baseline_median:+.3f}; "
                f"p95_ms: uninstrumented={_percentile(uninstrumented, 0.95):.3f}, "
                f"instrumented={_percentile(instrumented, 0.95):.3f}; "
                f"cold_insert_median_ms={statistics.median(cold_insert_samples):.3f}, "
                f"cold_insert_p95_ms={_percentile(cold_insert_samples, 0.95):.3f}"
            )
