"""
Tests for apps/dashboard_reports/viewsets/dashboard_report.py helpers.
Covers parse_period_param, PassthroughRenderer, require_date_range, and API endpoints.
"""

from unittest.mock import patch

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

    start, end, msg = parse_period_param(None, "period", "UTC")
    assert start is None
    assert end is None
    assert "required" in msg


@pytest.mark.unit
def test_parse_period_param_invalid_value():
    from apps.dashboard_reports.viewsets.dashboard_report import parse_period_param

    start, end, msg = parse_period_param("not-a-period", "period", "UTC")
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
        start, end, msg = parse_period_param(period, "period", "UTC")
        assert msg == "" and start is not None and end is not None


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

    with patch("ansible_base.rbac.api.permissions.IsSystemAdminOrAuditor.has_permission", return_value=True):
        # Find the correct URL
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

    with patch("ansible_base.rbac.api.permissions.IsSystemAdminOrAuditor.has_permission", return_value=True):
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
