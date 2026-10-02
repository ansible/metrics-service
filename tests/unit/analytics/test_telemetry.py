"""Tests for analytics Prometheus usage telemetry."""

from unittest.mock import patch

import pytest

from apps.analytics.telemetry import aggregate_analytics_usage, record_collector_get

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_record_collector_get_uses_canonical_public_name():
    with (
        patch("apps.analytics.telemetry.ANALYTICS_REQUESTS") as requests,
        patch("apps.analytics.telemetry.ANALYTICS_REQUEST_DURATION") as duration,
    ):
        record_collector_get("controller.config", 12.5)

    requests.labels.assert_called_once_with(collector="controller.config")
    requests.labels.return_value.inc.assert_called_once_with()
    duration.labels.assert_called_once_with(collector="controller.config")
    duration.labels.return_value.observe.assert_called_once_with(12.5)


def test_record_collector_get_rejects_unknown_label():
    with (
        patch("apps.analytics.telemetry.ANALYTICS_REQUESTS") as requests,
        patch("apps.analytics.telemetry.ANALYTICS_REQUEST_DURATION") as duration,
    ):
        record_collector_get("customer-supplied", 12.5)

    requests.labels.assert_not_called()
    duration.labels.assert_not_called()


def test_record_collector_get_swallows_metric_failure():
    with (
        patch("apps.analytics.telemetry.ANALYTICS_REQUESTS.labels", side_effect=RuntimeError("registry down")),
        patch("apps.analytics.telemetry.logger.exception") as log_exception,
    ):
        record_collector_get("controller.config", 12.5)

    log_exception.assert_called_once()


def test_recorded_metrics_are_visible_through_existing_export(authenticated_client):
    record_collector_get("controller.config", 12.5)

    response = authenticated_client.get("/api/v1/metrics")

    assert response.status_code == 200
    assert b"analytics_collector_get_requests_total" in response.content
    assert b'collector="controller.config"' in response.content


def test_aggregate_analytics_usage_derives_average_from_exported_sum_and_count():
    exposition = b"""# HELP analytics_collector_get_requests_total requests
# TYPE analytics_collector_get_requests_total counter
analytics_collector_get_requests_total{collector="controller.config"} 2.0
# HELP analytics_collector_get_duration_milliseconds duration
# TYPE analytics_collector_get_duration_milliseconds histogram
analytics_collector_get_duration_milliseconds_count{collector="controller.config"} 2.0
analytics_collector_get_duration_milliseconds_sum{collector="controller.config"} 31.0
"""

    with patch("apps.analytics.telemetry.generate_latest", return_value=exposition):
        result = aggregate_analytics_usage()

    assert result == {
        "controller.config": {
            "request_count": 2,
            "duration_ms_total": 31.0,
            "duration_ms_average": 15.5,
        }
    }


def test_aggregate_analytics_usage_rejects_sensitive_or_unknown_labels():
    exposition = b"""# TYPE analytics_collector_get_requests_total counter
analytics_collector_get_requests_total{collector="controller.config",organization="secret"} 4.0
analytics_collector_get_requests_total{collector="customer-supplied"} 3.0
"""

    with patch("apps.analytics.telemetry.generate_latest", return_value=exposition):
        result = aggregate_analytics_usage()

    assert result == {}


def test_aggregate_analytics_usage_returns_empty_for_no_samples():
    with patch("apps.analytics.telemetry.generate_latest", return_value=b"# TYPE unrelated gauge\nunrelated 1\n"):
        assert aggregate_analytics_usage() == {}


def test_aggregate_analytics_usage_returns_empty_on_scrape_failure():
    with (
        patch("apps.analytics.telemetry.generate_latest", side_effect=RuntimeError("scrape failed")),
        patch("apps.analytics.telemetry.logger.exception") as log_exception,
    ):
        result = aggregate_analytics_usage()

    assert result == {}
    log_exception.assert_called_once()
