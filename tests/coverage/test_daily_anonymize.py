"""
Unit tests for apps/tasks/collectors/daily_anonymize_and_prepare.py.
Targets 52% → ~90% coverage.
"""

from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import pytest
from django.utils import timezone


# ---------------------------------------------------------------------------
# random_offset helper
# ---------------------------------------------------------------------------
@pytest.mark.unit
def test_random_offset_in_range():
    from apps.tasks.collectors.daily_anonymize_and_prepare import random_offset

    for _ in range(10):
        offset = random_offset()
        assert 1 <= offset <= 240


# ---------------------------------------------------------------------------
# daily_anonymize_and_prepare — no summary (DoesNotExist)
# ---------------------------------------------------------------------------
@pytest.mark.unit
@pytest.mark.django_db
def test_daily_anonymize_no_summary():
    from apps.tasks.models import DailyMetricsSummary
    from apps.tasks.collectors.daily_anonymize_and_prepare import daily_anonymize_and_prepare

    yesterday = timezone.now().date() - timedelta(days=1)
    DailyMetricsSummary.objects.filter(summary_date=yesterday).delete()

    result = daily_anonymize_and_prepare()
    assert result["status"] == "error"
    assert "No daily summary found" in result["error"]


@pytest.mark.unit
@pytest.mark.django_db
def test_daily_anonymize_specific_date_no_summary():
    from apps.tasks.models import DailyMetricsSummary
    from apps.tasks.collectors.daily_anonymize_and_prepare import daily_anonymize_and_prepare

    specific_date = date(2020, 1, 15)
    DailyMetricsSummary.objects.filter(summary_date=specific_date).delete()

    result = daily_anonymize_and_prepare(summary_date="2020-01-15")
    assert result["status"] == "error"
    assert "No daily summary found" in result["error"]


# ---------------------------------------------------------------------------
# daily_anonymize_and_prepare — success path
# ---------------------------------------------------------------------------
@pytest.mark.unit
@pytest.mark.django_db
def test_daily_anonymize_success():
    from apps.tasks.models import DailyMetricsSummary, AnonymizedMetricsPayload
    from apps.tasks.collectors.daily_anonymize_and_prepare import daily_anonymize_and_prepare

    specific_date = date(2024, 3, 15)
    DailyMetricsSummary.objects.filter(summary_date=specific_date).delete()

    summary = DailyMetricsSummary.objects.create(
        summary_date=specific_date,
        status="aggregated",
        aggregated_metrics={"unified_jobs": {}, "job_host_summary_service": {}},
    )

    mock_anonymized = {"data": {"metrics": []}, "salt": "test-salt"}

    with patch("metrics_utility.anonymized_rollups.anonymize_rollups", return_value=mock_anonymized):
        result = daily_anonymize_and_prepare(summary_date="2024-03-15")

    assert result["status"] == "success"
    assert "payload_id" in result
    assert result["summary_date"] == "2024-03-15"

    # Verify payload was created
    assert AnonymizedMetricsPayload.objects.filter(summary_date=specific_date).exists()

    # Verify summary was updated
    summary.refresh_from_db()
    assert summary.status == "anonymized"


# ---------------------------------------------------------------------------
# daily_anonymize_and_prepare — exception handling
# ---------------------------------------------------------------------------
@pytest.mark.unit
@pytest.mark.django_db
def test_daily_anonymize_exception_in_anonymize():
    from apps.tasks.models import DailyMetricsSummary
    from apps.tasks.collectors.daily_anonymize_and_prepare import daily_anonymize_and_prepare

    specific_date = date(2024, 4, 10)
    DailyMetricsSummary.objects.filter(summary_date=specific_date).delete()
    DailyMetricsSummary.objects.create(
        summary_date=specific_date,
        status="aggregated",
        aggregated_metrics={},
    )

    with patch("metrics_utility.anonymized_rollups.anonymize_rollups", side_effect=RuntimeError("anonymize failed")):
        result = daily_anonymize_and_prepare(summary_date="2024-04-10")

    assert result["status"] == "error"
    assert "Anonymization failed" in result["error"]
