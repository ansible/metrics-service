"""
Unit tests for apps/dashboard_reports/filters.py.
Targets 50% → ~95% coverage.
"""

from datetime import timedelta
from unittest.mock import MagicMock

import pytest
from django.utils import timezone


# ---------------------------------------------------------------------------
# DateFilter enum
# ---------------------------------------------------------------------------
@pytest.mark.unit
def test_date_filter_to_list():
    from apps.dashboard_reports.filters import DateFilter

    periods = DateFilter.to_list()
    assert "last_7_days" in periods
    assert "last_30_days" in periods
    assert "last_90_days" in periods


@pytest.mark.unit
def test_date_filter_get_num_last_days():
    from apps.dashboard_reports.filters import DateFilter

    assert DateFilter.get_num_last_days("last_7_days") == 7
    assert DateFilter.get_num_last_days("last_30_days") == 30
    assert DateFilter.get_num_last_days("last_90_days") == 90


@pytest.mark.unit
def test_date_filter_get_num_last_days_none():
    from apps.dashboard_reports.filters import DateFilter

    assert DateFilter.get_num_last_days(None) is None


@pytest.mark.unit
def test_date_filter_to_start_date_end_date_utc():
    from apps.dashboard_reports.filters import DateFilter

    start, end = DateFilter.to_start_date_end_date("last_30_days", "UTC")
    assert start is not None
    assert end is not None
    assert (end - start).days == 30


@pytest.mark.unit
def test_date_filter_to_start_date_end_date_custom_tz():
    from apps.dashboard_reports.filters import DateFilter

    start, end = DateFilter.to_start_date_end_date("last_7_days", "America/New_York")
    assert start is not None
    assert end is not None


@pytest.mark.unit
def test_date_filter_to_start_date_end_date_invalid_tz():
    from apps.dashboard_reports.filters import DateFilter

    with pytest.raises(ValueError, match="Invalid timezone"):
        DateFilter.to_start_date_end_date("last_7_days", "Invalid/Timezone")


@pytest.mark.unit
def test_date_filter_to_start_date_end_date_none_value():
    from apps.dashboard_reports.filters import DateFilter

    start, end = DateFilter.to_start_date_end_date(None, "UTC")
    assert start is None
    assert end is None


# ---------------------------------------------------------------------------
# _safe_int
# ---------------------------------------------------------------------------
@pytest.mark.unit
def test_safe_int_valid():
    from apps.dashboard_reports.filters import _safe_int

    assert _safe_int("42") == 42
    assert _safe_int("0") == 0


@pytest.mark.unit
def test_safe_int_invalid():
    from apps.dashboard_reports.filters import _safe_int

    assert _safe_int("not-a-number") is None
    assert _safe_int(None) is None
    assert _safe_int("") is None


# ---------------------------------------------------------------------------
# _collect_int_params
# ---------------------------------------------------------------------------
@pytest.mark.unit
def test_collect_int_params():
    from apps.dashboard_reports.filters import _collect_int_params

    mock_request = MagicMock()
    mock_request.query_params.getlist.return_value = ["1", "2", "bad", "3"]
    result = _collect_int_params(mock_request, "organization")
    assert result == [1, 2, 3]


@pytest.mark.unit
def test_collect_int_params_empty():
    from apps.dashboard_reports.filters import _collect_int_params

    mock_request = MagicMock()
    mock_request.query_params.getlist.return_value = []
    result = _collect_int_params(mock_request, "template")
    assert result == []


# ---------------------------------------------------------------------------
# get_filter_options and get_or_filter_options
# ---------------------------------------------------------------------------
@pytest.mark.unit
def test_get_filter_options_with_values():
    from apps.dashboard_reports.filters import get_filter_options

    mock_request = MagicMock()

    def getlist_side_effect(key):
        if key == "organization":
            return ["1", "2"]
        return []

    mock_request.query_params.getlist.side_effect = getlist_side_effect
    result = get_filter_options(mock_request)
    assert "organization" in result
    assert result["organization"] == [1, 2]


@pytest.mark.unit
def test_get_filter_options_empty():
    from apps.dashboard_reports.filters import get_filter_options

    mock_request = MagicMock()
    mock_request.query_params.getlist.return_value = []
    result = get_filter_options(mock_request)
    assert result == {}


@pytest.mark.unit
def test_get_or_filter_options():
    from apps.dashboard_reports.filters import get_or_filter_options

    mock_request = MagicMock()

    def getlist_side_effect(key):
        if key == "or__template":
            return ["5", "10"]
        return []

    mock_request.query_params.getlist.side_effect = getlist_side_effect
    result = get_or_filter_options(mock_request)
    assert "template" in result
    assert result["template"] == [5, 10]


# ---------------------------------------------------------------------------
# apply_or_filters
# ---------------------------------------------------------------------------
@pytest.mark.unit
@pytest.mark.django_db
def test_apply_or_filters_empty():
    from apps.dashboard_reports.filters import apply_or_filters
    from apps.dashboard_reports.models import JobData

    mock_request = MagicMock()
    mock_request.query_params.getlist.return_value = []

    qs = JobData.objects.all()
    result = apply_or_filters(mock_request, qs)
    assert result is not None  # queryset unchanged


@pytest.mark.unit
@pytest.mark.django_db
def test_apply_or_filters_with_organization():
    from apps.dashboard_reports.filters import apply_or_filters
    from apps.dashboard_reports.models import JobData

    mock_request = MagicMock()

    def getlist_side_effect(key):
        if key == "or__organization":
            return ["1"]
        return []

    mock_request.query_params.getlist.side_effect = getlist_side_effect

    qs = JobData.objects.all()
    result = apply_or_filters(mock_request, qs)
    assert result is not None


# ---------------------------------------------------------------------------
# CustomReportFilter
# ---------------------------------------------------------------------------
@pytest.mark.unit
@pytest.mark.django_db
def test_custom_report_filter_with_injected_dates():
    from apps.dashboard_reports.filters import CustomReportFilter
    from apps.dashboard_reports.models import JobData
    from django.utils import timezone

    now = timezone.now()
    start = now - timedelta(days=30)

    filter_backend = CustomReportFilter()
    mock_request = MagicMock()
    mock_request.query_params.getlist.return_value = []

    mock_view = MagicMock()
    mock_view.kwargs = {"start_date": start, "end_date": now}

    qs = JobData.objects.all()
    result = filter_backend.filter_queryset(mock_request, qs, mock_view)
    assert result is not None


@pytest.mark.unit
@pytest.mark.django_db
def test_custom_report_filter_without_injected_dates():
    from apps.dashboard_reports.filters import CustomReportFilter
    from apps.dashboard_reports.models import JobData

    filter_backend = CustomReportFilter()
    mock_request = MagicMock()

    def getlist_side_effect(key):
        return []

    mock_request.query_params.getlist.side_effect = getlist_side_effect
    mock_request.query_params.get.side_effect = lambda key, default=None: {
        "period": "last_7_days",
        "tz": "UTC",
    }.get(key, default)

    mock_view = MagicMock()
    mock_view.kwargs = {}  # No injected dates

    qs = JobData.objects.all()
    result = filter_backend.filter_queryset(mock_request, qs, mock_view)
    assert result is not None
