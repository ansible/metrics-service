from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest
from django.http import QueryDict
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory

from apps.dashboard_reports.viewsets import DashboardReportViewSet
from apps.dashboard_reports.viewsets.dashboard_report import parse_date_param
from tests.unit.dashboard_reports.conftest import DummyView


# Unit tests for parse_date_param function
@pytest.mark.unit
class TestParseDateParam:
    # Test valid ISO date string
    def test_valid_iso_date(self):
        date_str = "2026-03-11T12:34:56"
        result, msg = parse_date_param(date_str, "start")
        assert isinstance(result, datetime)
        assert msg == ""
        assert result == datetime.fromisoformat(date_str)

    # Test invalid date string
    def test_invalid_date(self):
        date_str = "not-a-date"
        result, msg = parse_date_param(date_str, "start")
        assert result is None
        assert "Invalid start format" in msg

    # Test empty string
    def test_empty_string(self):
        result, msg = parse_date_param("", "end")
        assert result is None
        assert msg == "end is required"

    # Test None as input
    def test_none_string(self):
        result, msg = parse_date_param(None, "end")
        assert result is None
        assert msg == "end is required"

    # Test leap year date
    def test_leap_year(self):
        date_str = "2024-02-29T00:00:00"
        result, msg = parse_date_param(date_str, "start")
        assert isinstance(result, datetime)
        assert msg == ""
        assert result == datetime.fromisoformat(date_str)

    # Test ISO date with timezone
    def test_timezone(self):
        date_str = "2026-03-11T12:34:56+00:00"
        result, msg = parse_date_param(date_str, "start")
        assert isinstance(result, datetime)
        assert msg == ""
        assert result == datetime.fromisoformat(date_str)

    # Test boundary date
    def test_boundary(self):
        date_str = "1970-01-01T00:00:00"
        result, msg = parse_date_param(date_str, "start")
        assert isinstance(result, datetime)
        assert msg == ""
        assert result == datetime.fromisoformat(date_str)


# Unit tests for require_date_range decorator
@pytest.mark.unit
class TestRequireDateRange:
    @pytest.fixture
    def factory(self):
        return APIRequestFactory()

    # Test valid start/end dates
    def test_valid_dates(self, factory):
        view = DummyView()
        request = factory.get("/", {"start_date": "2026-03-11T12:00:00", "end_date": "2026-03-12T12:00:00"})
        view.request = request
        response = view.view(request)
        assert response.status_code == 200
        assert response.data["success"] is True
        assert view.called

    # Test missing start date
    def test_missing_start(self, factory):
        view = DummyView()
        request = factory.get("/", {"end_date": "2026-03-12T12:00:00"})
        view.request = request
        response = view.view(request)
        assert response.status_code == 400
        assert "start_date is required" in response.data["error"]
        assert not view.called

    # Test missing end date
    def test_missing_end(self, factory):
        view = DummyView()
        request = factory.get("/", {"start_date": "2026-03-11T12:00:00"})
        view.request = request
        response = view.view(request)
        assert response.status_code == 400
        assert "end_date is required" in response.data["error"]
        assert not view.called

    # Test invalid start date format
    def test_invalid_start_format(self, factory):
        view = DummyView()
        request = factory.get("/", {"start_date": "bad-date", "end_date": "2026-03-12T12:00:00"})
        view.request = request
        response = view.view(request)
        assert response.status_code == 400
        assert "Invalid start_date format" in response.data["error"]
        assert not view.called

    # Test invalid end date format
    def test_invalid_end_format(self, factory):
        view = DummyView()
        request = factory.get("/", {"start_date": "2026-03-11T12:00:00", "end_date": "bad-date"})
        view.request = request
        response = view.view(request)
        assert response.status_code == 400
        assert "Invalid end_date format" in response.data["error"]
        assert not view.called

    # Test leap year dates
    def test_leap_year(self, factory):
        view = DummyView()
        request = factory.get("/", {"start_date": "2024-02-29T00:00:00", "end_date": "2024-03-01T00:00:00"})
        view.request = request
        response = view.view(request)
        assert response.status_code == 200
        assert response.data["success"] is True
        assert view.called

    # Test timezone-aware dates
    def test_timezone(self, factory):
        view = DummyView()
        request = factory.get("/", {"start_date": "2026-03-11T12:00:00+00:00", "end_date": "2026-03-12T12:00:00+00:00"})
        view.request = request
        response = view.view(request)
        assert response.status_code == 200
        assert response.data["success"] is True
        assert view.called


# Unit tests for DashboardReportViewSet methods
@pytest.mark.django_db
@pytest.mark.unit
class TestDashboardReportViewSet:
    @pytest.fixture
    def factory(self):
        return APIRequestFactory()

    @pytest.fixture
    def viewset(self):
        return DashboardReportViewSet()

    # Test default serializer class
    def test_get_serializer_class_default(self, viewset):
        viewset.action = None
        assert viewset.get_serializer_class() == viewset.serializer_class

    # Test details serializer class
    def test_get_serializer_class_details(self, viewset):
        viewset.action = "details"
        from apps.dashboard_reports.serializers import ReportDetailSerializer

        assert viewset.get_serializer_class() == ReportDetailSerializer

    # Test get_queryset with mocks
    @patch("apps.dashboard_reports.viewsets.dashboard_report.SubscriptionCost.get")
    @patch("apps.dashboard_reports.viewsets.dashboard_report.JobData.objects")
    def test_get_queryset(self, mock_jobdata, mock_subcost, viewset):
        mock_subcost.return_value.cost_employee_per_minute = 1
        mock_subcost.return_value.per_second_subscription_cost.return_value = 0.01
        mock_subcost.return_value.include_template_creation_time_in_costs = True
        mock_jobdata.prefetch_related.return_value.values.return_value.annotate.return_value = ["mocked"]
        viewset.kwargs = {"start_date": None, "end_date": None}
        result = viewset.get_queryset()
        assert result == ["mocked"]

    # Test _get_date_range_and_kind with None
    def test__get_date_range_and_kind_none(self, viewset):
        viewset.kwargs = {"start_date": None, "end_date": None}
        start, end, kind = viewset._get_date_range_and_kind()
        assert start is None and end is None and kind is None

    # Test _get_date_range_and_kind for hour
    def test__get_date_range_and_kind_hour(self, viewset):
        viewset.kwargs = {
            "start_date": datetime(2026, 3, 11, 10, 0, tzinfo=UTC),
            "end_date": datetime(2026, 3, 11, 20, 0, tzinfo=UTC),
        }
        start, end, kind = viewset._get_date_range_and_kind()
        assert kind == "hour"

    # Test _get_date_range_and_kind for day
    def test__get_date_range_and_kind_day(self, viewset):
        viewset.kwargs = {
            "start_date": datetime(2026, 3, 1, 0, 0, tzinfo=UTC),
            "end_date": datetime(2026, 3, 11, 0, 0, tzinfo=UTC),
        }
        start, end, kind = viewset._get_date_range_and_kind()
        assert kind == "day"

    # Test _get_date_range_and_kind for month
    def test__get_date_range_and_kind_month(self, viewset):
        viewset.kwargs = {
            "start_date": datetime(2026, 1, 1, 0, 0, tzinfo=UTC),
            "end_date": datetime(2026, 3, 11, 0, 0, tzinfo=UTC),
        }
        start, end, kind = viewset._get_date_range_and_kind()
        assert kind == "month"

    # Test _get_date_range_and_kind for year
    def test__get_date_range_and_kind_year(self, viewset):
        # Use dates that span different years and months
        viewset.kwargs = {
            "start_date": datetime(2025, 1, 1, 0, 0, tzinfo=UTC),
            "end_date": datetime(2026, 12, 31, 0, 0, tzinfo=UTC),
        }
        start, end, kind = viewset._get_date_range_and_kind()
        assert kind == "year"

    # Test _prepare_chart_querysets with mocks
    @patch("apps.dashboard_reports.viewsets.dashboard_report.JobData.objects")
    def test__prepare_chart_querysets(self, mock_jobdata, viewset, factory):
        mock_qs = MagicMock()
        mock_jobdata.all.return_value = mock_qs
        mock_qs.values.return_value.filter.return_value = mock_qs
        mock_qs.annotate.return_value.values.return_value.order_by.return_value = mock_qs
        # Use MagicMock for request with QueryDict for query_params
        mock_request = MagicMock()
        mock_request.query_params = QueryDict()
        viewset.request = mock_request
        viewset.kwargs = {
            "start_date": datetime(2026, 3, 11, 0, 0, tzinfo=UTC),
            "end_date": datetime(2026, 3, 12, 0, 0, tzinfo=UTC),
        }
        job_qs, host_qs = viewset._prepare_chart_querysets("day")
        assert isinstance(job_qs, MagicMock | list)
        assert isinstance(host_qs, MagicMock | list)

    # Test _format_chart_result
    def test__format_chart_result(self, viewset):
        class Dummy:
            def __init__(self, term, runs, hosts):
                self.term = term
                self.runs = runs
                self.hosts = hosts

        data = [Dummy("2026-03-11", 5, 10), Dummy("2026-03-12", 3, 7)]
        result = viewset._format_chart_result(data)
        assert result["job_chart"]["items"][0]["label"] == "2026-03-11"
        assert result["job_chart"]["items"][0]["value"] == 5
        assert result["host_chart"]["items"][1]["value"] == 7

    # Test get_chart_data with mocks
    @patch("apps.dashboard_reports.viewsets.dashboard_report.generate_series")
    @patch.object(DashboardReportViewSet, "_prepare_chart_querysets")
    def test_get_chart_data(self, mock_prepare, mock_gen, viewset):
        viewset.kwargs = {
            "start_date": datetime(2026, 3, 11, 0, 0, tzinfo=UTC),
            "end_date": datetime(2026, 3, 12, 0, 0, tzinfo=UTC),
        }
        # Mock QuerySet-like objects for Subquery
        mock_job_qs = MagicMock()
        mock_host_qs = MagicMock()
        mock_job_qs.query = MagicMock()
        mock_host_qs.query = MagicMock()
        mock_prepare.return_value = (mock_job_qs, mock_host_qs)
        dummy_seq = [MagicMock(term="2026-03-11", runs=5, hosts=10)]
        mock_gen.return_value.annotate.return_value = dummy_seq
        result = viewset.get_chart_data()
        assert result["job_chart"]["items"][0]["label"] == "2026-03-11"
        assert result["job_chart"]["items"][0]["value"] == 5

    # Test details endpoint logic with mocks
    @patch("apps.dashboard_reports.viewsets.dashboard_report.JobData.objects")
    @patch("apps.dashboard_reports.viewsets.dashboard_report.JobHostSummary.unique_count")
    @patch("apps.dashboard_reports.viewsets.dashboard_report.get_filter_options")
    @patch.object(DashboardReportViewSet, "get_chart_data")
    @patch.object(DashboardReportViewSet, "get_serializer")
    def test_details(self, mock_serializer, mock_chart, mock_filter, mock_unique, mock_jobdata, viewset, factory):
        class TestViewSet(DashboardReportViewSet):
            def details(self, request, *args, **kwargs):
                return super().details.__wrapped__(self, request, *args, **kwargs)

        test_viewset = TestViewSet()
        mock_jobdata.all.return_value = MagicMock()
        mock_filter.return_value = {}
        mock_unique.return_value = 2
        mock_chart.return_value = {
            "job_chart": {"kind": "day", "items": []},
            "host_chart": {"kind": "day", "items": []},
        }
        mock_serializer.return_value.data = {
            "total_runs": 10,
            "top_users": [],
            "top_projects": [],
            "total_number_of_unique_hosts": 2,
        }
        dt_start = datetime(2026, 3, 11, 0, 0, tzinfo=UTC)
        dt_end = datetime(2026, 3, 12, 0, 0, tzinfo=UTC)
        test_viewset.kwargs = {
            "start_date": dt_start,
            "end_date": dt_end,
        }
        request = factory.get("/", {"start": dt_start.isoformat(), "end": dt_end.isoformat()})
        # Use MagicMock to wrap request since query_params is a read-only property
        mock_request = MagicMock()
        mock_request.GET = request.GET
        mock_request.query_params = request.GET
        test_viewset.request = mock_request
        response = test_viewset.details(mock_request, start_date=dt_start, end_date=dt_end)
        assert isinstance(response, Response)
        assert response.status_code == 200
        assert response.data["total_number_of_unique_hosts"] == 2
