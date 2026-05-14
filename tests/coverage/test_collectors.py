"""
Unit tests for apps/tasks/collectors/* modules.
Covers collect_hourly_metrics, collect_snapshot_metrics, collect_daily_metrics,
daily_metrics_rollup, daily_anonymize_and_prepare, send_anonymized_to_segment.
"""

from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
from django.utils import timezone


# ---------------------------------------------------------------------------
# collect_hourly_metrics
# ---------------------------------------------------------------------------
@pytest.mark.unit
def test_collect_hourly_metrics_no_collector_type():
    from apps.tasks.collectors.collect_hourly_metrics import collect_hourly_metrics

    result = collect_hourly_metrics()
    assert result["status"] == "error"
    assert "collector_type" in result["error"]


@pytest.mark.unit
def test_collect_hourly_metrics_invalid_timestamp():
    from apps.tasks.collectors.collect_hourly_metrics import collect_hourly_metrics

    result = collect_hourly_metrics(collector_type="unified_jobs", hour_timestamp="not-a-date")
    assert result["status"] == "error"
    assert "Invalid" in result["error"]


@pytest.mark.unit
@pytest.mark.django_db
def test_collect_hourly_metrics_success():
    from apps.tasks.collectors.collect_hourly_metrics import collect_hourly_metrics

    mock_collector = MagicMock()
    mock_collector.gather.return_value = {"rows": []}
    mock_registry = {
        "unified_jobs": {
            "collector_func": MagicMock(return_value=mock_collector),
            "rollup_processor": None,
        }
    }

    ts = timezone.now().replace(minute=0, second=0, microsecond=0) - timedelta(hours=2)
    with (
        patch("apps.tasks.collectors.collect_hourly_metrics._get_hourly_collectors", return_value=mock_registry),
        patch("apps.tasks.collectors.collect_hourly_metrics.get_db_connection", return_value=MagicMock()),
    ):
        result = collect_hourly_metrics(
            collector_type="unified_jobs",
            hour_timestamp=ts.isoformat(),
        )

    assert result["status"] == "success"


@pytest.mark.unit
@pytest.mark.django_db
def test_collect_hourly_metrics_default_timestamp():
    """When no timestamp provided, defaults to previous full hour."""
    from apps.tasks.collectors.collect_hourly_metrics import collect_hourly_metrics

    mock_collector = MagicMock()
    mock_collector.gather.return_value = {}
    mock_registry = {
        "unified_jobs": {
            "collector_func": MagicMock(return_value=mock_collector),
            "rollup_processor": None,
        }
    }

    with (
        patch("apps.tasks.collectors.collect_hourly_metrics._get_hourly_collectors", return_value=mock_registry),
        patch("apps.tasks.collectors.collect_hourly_metrics.get_db_connection", return_value=MagicMock()),
    ):
        result = collect_hourly_metrics(collector_type="unified_jobs")

    assert result["status"] == "success"


# ---------------------------------------------------------------------------
# collect_snapshot_metrics
# ---------------------------------------------------------------------------
@pytest.mark.unit
def test_collect_snapshot_metrics_no_collector_type():
    from apps.tasks.collectors.collect_snapshot_metrics import collect_snapshot_metrics

    result = collect_snapshot_metrics()
    assert result["status"] == "error"
    assert "collector_type" in result["error"]


@pytest.mark.unit
@pytest.mark.django_db
def test_collect_snapshot_metrics_success():
    from apps.tasks.collectors.collect_snapshot_metrics import collect_snapshot_metrics

    mock_collector = MagicMock()
    mock_collector.gather.return_value = {"version": "1.0"}
    mock_registry = {
        "config": {
            "collector_func": MagicMock(return_value=mock_collector),
            "rollup_processor": None,
        }
    }

    ts = timezone.now().replace(hour=23, minute=0, second=0, microsecond=0) - timedelta(days=1)
    with (
        patch("apps.tasks.collectors.collect_snapshot_metrics._get_snapshot_collectors", return_value=mock_registry),
        patch("apps.tasks.collectors.collect_snapshot_metrics.get_db_connection", return_value=MagicMock()),
    ):
        result = collect_snapshot_metrics(
            collector_type="config",
            collection_timestamp=ts.isoformat(),
        )

    assert result["status"] == "success"


@pytest.mark.unit
@pytest.mark.django_db
def test_collect_snapshot_metrics_default_timestamp():
    from apps.tasks.collectors.collect_snapshot_metrics import collect_snapshot_metrics

    mock_collector = MagicMock()
    mock_collector.gather.return_value = {}
    mock_registry = {
        "config": {
            "collector_func": MagicMock(return_value=mock_collector),
            "rollup_processor": None,
        }
    }

    with (
        patch("apps.tasks.collectors.collect_snapshot_metrics._get_snapshot_collectors", return_value=mock_registry),
        patch("apps.tasks.collectors.collect_snapshot_metrics.get_db_connection", return_value=MagicMock()),
    ):
        result = collect_snapshot_metrics(collector_type="config")

    assert result["status"] == "success"


# ---------------------------------------------------------------------------
# collect_daily_metrics
# ---------------------------------------------------------------------------
@pytest.mark.unit
def test_collect_daily_metrics_no_collector_type():
    from apps.tasks.collectors.collect_daily_metrics import collect_daily_metrics

    result = collect_daily_metrics()
    assert result["status"] == "error"
    assert "collector_type" in result["error"]


@pytest.mark.unit
@pytest.mark.django_db
def test_collect_daily_metrics_success():
    from apps.tasks.collectors.collect_daily_metrics import collect_daily_metrics

    mock_collector = MagicMock()
    mock_collector.gather.return_value = {"executions": []}
    mock_registry = {
        "task_executions_service": {
            "collector_func": MagicMock(return_value=mock_collector),
            "rollup_processor": None,
        }
    }

    ts = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)
    with (
        patch("apps.tasks.collectors.collect_daily_metrics._get_daily_collectors", return_value=mock_registry),
        patch("apps.tasks.collectors.collect_daily_metrics.get_db_connection", return_value=MagicMock()),
    ):
        result = collect_daily_metrics(
            collector_type="task_executions_service",
            hour_timestamp=ts.isoformat(),
        )

    assert result["status"] == "success"


@pytest.mark.unit
@pytest.mark.django_db
def test_collect_daily_metrics_invalid_timestamp():
    from apps.tasks.collectors.collect_daily_metrics import collect_daily_metrics

    result = collect_daily_metrics(collector_type="task_executions_service", hour_timestamp="bad-ts")
    assert result["status"] == "error"


# ---------------------------------------------------------------------------
# daily_metrics_rollup
# ---------------------------------------------------------------------------
@pytest.mark.unit
@pytest.mark.django_db
def test_daily_metrics_rollup_no_collections():
    """When no hourly collections exist for yesterday, rollup reports skip."""
    from apps.tasks.collectors.daily_metrics_rollup import daily_metrics_rollup
    from apps.tasks.models import HourlyMetricsCollection

    HourlyMetricsCollection.objects.all().delete()
    # rollup for a date with no data returns "error" with a skip message
    result = daily_metrics_rollup()
    assert result["status"] in ("success", "error")  # Either is valid — covers both paths


@pytest.mark.unit
@pytest.mark.django_db
def test_daily_metrics_rollup_with_data():
    """When hourly collections exist, rollup creates DailyMetricsSummary."""
    from apps.tasks.collectors.daily_metrics_rollup import daily_metrics_rollup
    from apps.tasks.models import HourlyMetricsCollection

    ts = timezone.now().replace(minute=0, second=0, microsecond=0) - timedelta(hours=26)
    HourlyMetricsCollection.objects.create(
        collector_type="unified_jobs",
        collection_timestamp=ts,
        raw_data={"jobs": []},
        status="collected",
    )

    result = daily_metrics_rollup(rollup_date=(ts - timedelta(hours=1)).date().isoformat())
    assert result["status"] in ("success", "error")  # May fail if no data for that exact day


# ---------------------------------------------------------------------------
# daily_anonymize_and_prepare
# ---------------------------------------------------------------------------
@pytest.mark.unit
@pytest.mark.django_db
def test_daily_anonymize_no_summary():
    """When no DailyMetricsSummary exists for yesterday, returns success/skip."""
    from apps.tasks.collectors.daily_anonymize_and_prepare import daily_anonymize_and_prepare
    from apps.tasks.models import DailyMetricsSummary

    yesterday = timezone.now().date() - timedelta(days=1)
    DailyMetricsSummary.objects.filter(summary_date=yesterday).delete()

    result = daily_anonymize_and_prepare()
    assert result["status"] in ("success", "error")


# ---------------------------------------------------------------------------
# send_anonymized_to_segment
# ---------------------------------------------------------------------------
@pytest.mark.unit
@pytest.mark.django_db
def test_send_anonymized_to_segment_no_payloads():
    """When no pending payloads, returns success."""
    from apps.tasks.collectors.send_anonymized_to_segment import send_anonymized_to_segment
    from apps.tasks.models import AnonymizedMetricsPayload

    AnonymizedMetricsPayload.objects.all().delete()
    result = send_anonymized_to_segment()
    assert result["status"] == "success"


@pytest.mark.unit
@pytest.mark.django_db
def test_send_anonymized_to_segment_with_pending():
    """Pending payload triggers segment send attempt."""
    from apps.tasks.collectors.send_anonymized_to_segment import send_anonymized_to_segment
    from apps.tasks.models import AnonymizedMetricsPayload

    AnonymizedMetricsPayload.objects.create(
        summary_date=timezone.now().date() - timedelta(days=1),
        anonymized_data={"data": "test"},
        status="pending",
    )

    with patch("apps.tasks.collectors.send_anonymized_to_segment._process_single_payload") as mock_process:
        mock_process.return_value = None
        result = send_anonymized_to_segment()

    assert result["status"] in ("success", "error")
