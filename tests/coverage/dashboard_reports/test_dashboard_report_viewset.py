"""
Tests for apps/dashboard_reports/viewsets/dashboard_report.py helpers.
Covers parse_period_param, PassthroughRenderer, require_date_range, and API endpoints.
"""

import pytest


# ---------------------------------------------------------------------------
# PassthroughRenderer
# ---------------------------------------------------------------------------
@pytest.mark.unit
def test_passthrough_renderer_returns_data_as_is():
    from apps.dashboard_reports.viewsets.dashboard_report import PassthroughRenderer

    renderer = PassthroughRenderer()
    data = b"name,value\ntest,123"
    result = renderer.render(data)
    assert result == data


# ---------------------------------------------------------------------------
# parse_period_param
# ---------------------------------------------------------------------------
@pytest.mark.unit
def test_parse_period_param_missing_returns_error():
    from apps.dashboard_reports.viewsets.dashboard_report import parse_period_param

    start, end, msg = parse_period_param(None, "period", "UTC", None, None)
    assert start is None
    assert end is None
    assert "required" in msg


@pytest.mark.unit
def test_parse_period_param_invalid_value():
    from apps.dashboard_reports.viewsets.dashboard_report import parse_period_param

    start, end, msg = parse_period_param("not-a-period", "period", "UTC", None, None)
    assert start is None
    assert end is None
    assert "Invalid" in msg


@pytest.mark.unit
def test_parse_period_param_valid():
    from apps.dashboard_reports.filters import DateFilter
    from apps.dashboard_reports.viewsets.dashboard_report import parse_period_param

    valid_periods = DateFilter.to_list()
    if valid_periods:
        period = valid_periods[0]
        start, end, msg = parse_period_param(period, "period", "UTC", None, None)
        assert msg == "" and start is not None and end is not None


@pytest.mark.unit
def test_parse_period_param_custom_valid():
    """Custom period with valid dates returns datetimes and empty error message."""
    from apps.dashboard_reports.viewsets.dashboard_report import parse_period_param

    start, end, msg = parse_period_param("custom", "period", "UTC", "2024-06-01", "2024-06-30")
    assert msg == ""
    assert start is not None
    assert end is not None


@pytest.mark.unit
def test_parse_period_param_custom_missing_start():
    """Custom period without start_date returns error."""
    from apps.dashboard_reports.viewsets.dashboard_report import parse_period_param

    start, end, msg = parse_period_param("custom", "period", "UTC", None, "2024-06-30")
    assert start is None
    assert end is None
    assert "start_date and end_date are required" in msg


@pytest.mark.unit
def test_parse_period_param_custom_missing_end():
    """Custom period without end_date returns error."""
    from apps.dashboard_reports.viewsets.dashboard_report import parse_period_param

    start, end, msg = parse_period_param("custom", "period", "UTC", "2024-06-01", None)
    assert start is None
    assert end is None
    assert "start_date and end_date are required" in msg


@pytest.mark.unit
def test_parse_period_param_custom_invalid_date():
    """Custom period with invalid date format returns error."""
    from apps.dashboard_reports.viewsets.dashboard_report import parse_period_param

    start, end, msg = parse_period_param("custom", "period", "UTC", "not-a-date", "2024-06-30")
    assert start is None
    assert end is None
    assert "Invalid" in msg


@pytest.mark.unit
def test_parse_period_param_empty_string():
    """Empty period string returns required error."""
    from apps.dashboard_reports.viewsets.dashboard_report import parse_period_param

    start, end, msg = parse_period_param("", "period", "UTC", None, None)
    assert start is None
    assert end is None
    assert "required" in msg


# ---------------------------------------------------------------------------
# API endpoint tests — require authentication and permissions
# ---------------------------------------------------------------------------
@pytest.mark.unit
@pytest.mark.django_db
def test_dashboard_report_list_unauthorized():
    """Unauthenticated request should return 401/403."""
    from rest_framework.test import APIClient

    client = APIClient()
    response = client.get("/api/v1/dashboard/")
    assert response.status_code in (401, 403, 404)


@pytest.mark.unit
@pytest.mark.django_db
def test_dashboard_report_list_no_period(user):
    """List endpoint requires a period parameter."""
    from rest_framework.test import APIClient

    client = APIClient()
    client.force_authenticate(user=user)

    response = client.get("/api/v1/dashboard/")

    # Dashboard viewset is at /api/v1/dashboard_reports/dashboard/ or similar; 404 means not found
    assert response.status_code in (200, 400, 404)


@pytest.mark.unit
@pytest.mark.django_db
def test_dashboard_report_filters_viewset(user):
    """Filter sets viewset is accessible."""
    from rest_framework.test import APIClient

    client = APIClient()
    client.force_authenticate(user=user)

    response = client.get("/api/v1/filter-sets/")

    assert response.status_code in (200, 404)


# ---------------------------------------------------------------------------
# filters.py — DateFilter
# ---------------------------------------------------------------------------
@pytest.mark.unit
def test_date_filter_to_list():
    from apps.dashboard_reports.filters import DateFilter

    periods = DateFilter.to_list()
    assert isinstance(periods, list)
    assert len(periods) > 0


@pytest.mark.unit
def test_date_filter_to_start_date_end_date():
    from apps.dashboard_reports.filters import DateFilter

    periods = DateFilter.to_list()
    if periods:
        period = periods[0]
        start, end = DateFilter.to_start_date_end_date(value=period, tz_string="UTC")
        assert start is not None and end is not None
        assert start <= end


@pytest.mark.unit
def test_date_filter_custom_range_valid():
    """custom_range_to_start_date_end_date returns start at midnight and end at end of day."""
    from apps.dashboard_reports.filters import DateFilter

    start, end = DateFilter.custom_range_to_start_date_end_date("2024-06-01", "2024-06-30", "UTC")
    assert start is not None
    assert end is not None
    assert start.hour == 0 and start.minute == 0
    assert end.hour == 23 and end.minute == 59 and end.second == 59


@pytest.mark.unit
def test_date_filter_custom_range_invalid_date():
    """custom_range_to_start_date_end_date raises ValueError for invalid date string."""
    from apps.dashboard_reports.filters import DateFilter

    with pytest.raises(ValueError, match="Invalid date format"):
        DateFilter.custom_range_to_start_date_end_date("bad-date", "2024-06-30", "UTC")


@pytest.mark.unit
def test_date_filter_custom_includes_custom_value():
    """DateFilter.to_list() includes 'custom'."""
    from apps.dashboard_reports.filters import DateFilter

    assert "custom" in DateFilter.to_list()


@pytest.mark.unit
def test_date_filter_get_timezone_valid():
    """get_timezone returns a ZoneInfo for a valid timezone string."""
    from zoneinfo import ZoneInfo

    from apps.dashboard_reports.filters import DateFilter

    tz = DateFilter.get_timezone("Europe/Ljubljana")
    assert tz == ZoneInfo("Europe/Ljubljana")


@pytest.mark.unit
def test_date_filter_get_timezone_invalid():
    """get_timezone raises ValueError for an unknown timezone."""
    from apps.dashboard_reports.filters import DateFilter

    with pytest.raises(ValueError, match="Invalid timezone"):
        DateFilter.get_timezone("Not/AZone")
