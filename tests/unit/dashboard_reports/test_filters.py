"""
Unit tests for apps.dashboard_reports.filters module.
"""

from unittest.mock import MagicMock, patch
from urllib.parse import urlencode

import pytest
from django.db import models
from django.http import QueryDict
from rest_framework.request import Request

from apps.dashboard_reports.filters import (
    CustomReportFilter,
    DateFilter,
    _safe_int,
    apply_or_filters,
    get_filter_options,
    get_or_filter_options,
)
from apps.dashboard_reports.viewsets.filter_options import FilterOptionsViewSet


@pytest.mark.unit
class TestDateFilter:
    """Tests for DateFilter enum methods."""

    def test_to_list_returns_all_values(self):
        """to_list returns all five period strings."""
        result = DateFilter.to_list()
        assert result == ["last_7_days", "last_14_days", "last_30_days", "last_60_days", "last_90_days"]

    @pytest.mark.parametrize(
        "value,expected",
        [
            ("last_7_days", 7),
            ("last_14_days", 14),
            ("last_30_days", 30),
            ("last_60_days", 60),
            ("last_90_days", 90),
        ],
    )
    def test_get_num_last_days_valid(self, value, expected):
        """get_num_last_days extracts the integer correctly."""
        assert DateFilter.get_num_last_days(value) == expected

    def test_get_num_last_days_none(self):
        """get_num_last_days returns None when value is None."""
        assert DateFilter.get_num_last_days(None) is None

    def test_to_start_date_end_date_returns_datetimes(self):
        """to_start_date_end_date returns (start, end) datetimes for a valid value."""
        start, end = DateFilter.to_start_date_end_date("last_7_days", "UTC")
        assert start is not None
        assert end is not None
        diff = end - start
        assert 6 <= diff.days <= 7

    def test_to_start_date_end_date_valid_timezone(self):
        """to_start_date_end_date respects a valid timezone."""
        start, end = DateFilter.to_start_date_end_date("last_30_days", "US/Eastern")
        assert start.tzinfo is not None
        assert end.tzinfo is not None

    def test_to_start_date_end_date_invalid_timezone_raises(self):
        """to_start_date_end_date raises ValueError for an unrecognised timezone."""
        with pytest.raises(ValueError, match="Invalid timezone"):
            DateFilter.to_start_date_end_date("last_7_days", "Not/AReal_Zone")

    def test_to_start_date_end_date_none_value_returns_none_pair(self):
        """to_start_date_end_date returns (None, None) when value is None."""
        start, end = DateFilter.to_start_date_end_date(None, "UTC")
        assert start is None
        assert end is None


@pytest.mark.unit
class TestSafeInt:
    """Tests for _safe_int helper function."""

    def test_valid_integer_string(self):
        """Test conversion of valid integer string."""
        assert _safe_int("42") == 42

    def test_valid_negative_integer_string(self):
        """Test conversion of valid negative integer string."""
        assert _safe_int("-10") == -10

    def test_valid_zero_string(self):
        """Test conversion of zero string."""
        assert _safe_int("0") == 0

    def test_valid_large_integer_string(self):
        """Test conversion of large integer string."""
        assert _safe_int("999999999") == 999999999

    def test_invalid_float_string(self):
        """Test that float string returns None."""
        assert _safe_int("3.14") is None

    def test_invalid_text_string(self):
        """Test that text string returns None."""
        assert _safe_int("abc") is None

    def test_invalid_empty_string(self):
        """Test that empty string returns None."""
        assert _safe_int("") is None

    def test_invalid_whitespace_string(self):
        """Test that whitespace string returns None."""
        assert _safe_int("   ") is None

    def test_invalid_mixed_string(self):
        """Test that mixed alphanumeric string returns None."""
        assert _safe_int("12abc") is None

    def test_none_value(self):
        """Test that None value returns None (TypeError handled)."""
        assert _safe_int(None) is None

    def test_integer_input(self):
        """Test that integer input is converted (int() handles int input)."""
        assert _safe_int(42) == 42

    def test_whitespace_around_number(self):
        """Test that whitespace around number is handled by int()."""
        assert _safe_int("  42  ") == 42

    def test_plus_sign_prefix(self):
        """Test that plus sign prefix works."""
        assert _safe_int("+10") == 10

    def test_leading_zeros(self):
        """Test that leading zeros work."""
        assert _safe_int("007") == 7


@pytest.mark.unit
@pytest.mark.django_db
class TestFilterOptionsViewSet:
    """Tests for FilterOptionsViewSet ORM-based interface.

    Uses AWXOrganization as a concrete stand-in since FilterOptionsViewSet.cache_model
    must be set by subclasses.
    """

    @pytest.fixture
    def viewset(self):
        from apps.dashboard_reports.models import AWXOrganization
        from apps.dashboard_reports.viewsets.organizations import OrganizationsViewSet

        vs = OrganizationsViewSet()
        vs.request = MagicMock()
        vs.kwargs = {}
        vs.format_kwarg = None
        return vs

    def test_get_queryset_returns_empty_qs(self, viewset):
        assert not viewset.get_queryset().exists()

    def test_retrieve_invalid_pk_string(self, viewset):
        request = MagicMock()
        response = viewset.retrieve(request, pk="invalid-int")
        assert response.status_code == 400

    def test_retrieve_pk_zero(self, viewset):
        request = MagicMock()
        response = viewset.retrieve(request, pk=0)
        assert response.status_code == 404

    def test_retrieve_pk_negative(self, viewset):
        request = MagicMock()
        response = viewset.retrieve(request, pk=-1)
        assert response.status_code == 404

    def test_retrieve_not_found(self, viewset):
        request = MagicMock()
        response = viewset.retrieve(request, pk=9999)
        assert response.status_code == 404
        assert "9999" in str(response.data)

    def test_not_found_msg(self, viewset):
        assert "42" in viewset.not_found_msg(42)


@pytest.mark.unit
class TestGetOrFilterOptions:
    """Tests for get_or_filter_options function."""

    def _mock_request(self, query_params: dict[str, list[str]]) -> MagicMock:
        mock_request = MagicMock()
        mock_request.query_params.getlist = lambda key: query_params.get(key, [])
        return mock_request

    def test_empty_params_returns_empty_dict(self):
        request = self._mock_request({})
        assert get_or_filter_options(request) == {}

    def test_single_or_organization(self):
        request = self._mock_request({"or__organization": ["1", "2"]})
        result = get_or_filter_options(request)
        assert result == {"organization": [1, 2]}

    def test_or_label_filter(self):
        request = self._mock_request({"or__label": ["5", "6"]})
        result = get_or_filter_options(request)
        assert result == {"label": [5, 6]}

    def test_or_template_filter(self):
        request = self._mock_request({"or__template": ["10"]})
        result = get_or_filter_options(request)
        assert result == {"template": [10]}

    def test_or_project_filter(self):
        request = self._mock_request({"or__project": ["100"]})
        result = get_or_filter_options(request)
        assert result == {"project": [100]}

    def test_invalid_or_values_skipped(self):
        request = self._mock_request({"or__organization": ["1", "abc", "2"]})
        result = get_or_filter_options(request)
        assert result == {"organization": [1, 2]}

    def test_and_fields_not_included(self):
        request = self._mock_request({"organization": ["1"], "or__organization": ["2"]})
        result = get_or_filter_options(request)
        assert "organization" in result
        assert result["organization"] == [2]


@pytest.mark.unit
class TestApplyOrFilters:
    def _make_request(self, params: dict) -> Request:
        request = MagicMock()
        request.query_params = QueryDict(urlencode(params, doseq=True))
        return request

    def test_no_or_filters_returns_queryset_unchanged(self):
        request = self._make_request({})
        mock_qs = MagicMock()
        result = apply_or_filters(request, mock_qs)
        assert result is mock_qs  # early return, queryset untouched

    def test_single_or_filter_applied(self):
        request = self._make_request({"or__organization": [1, 2]})
        mock_qs = MagicMock()
        filtered_qs = MagicMock()
        mock_qs.filter.return_value = filtered_qs

        result = apply_or_filters(request, mock_qs)

        mock_qs.filter.assert_called_once_with(models.Q(organization_id__in=[1, 2]))
        assert result is filtered_qs

    def test_multiple_or_filters_reduced(self):
        request = self._make_request(
            {
                "or__organization": [1],
                "or__project": [2],
            }
        )
        mock_qs = MagicMock()
        filtered_qs = MagicMock()
        mock_qs.filter.return_value = filtered_qs

        result = apply_or_filters(request, mock_qs)

        mock_qs.filter.assert_called_once()
        assert result is filtered_qs

    @patch("apps.dashboard_reports.filters.label_ids_to_job_data_ids")
    def test_or_label_filter_applied(self, mock_label_ids):
        """Label OR filter uses label_ids_to_job_data_ids to resolve job IDs."""
        mock_label_ids.return_value = [10, 20]
        request = self._make_request({"or__label": [5, 6]})
        mock_qs = MagicMock()
        filtered_qs = MagicMock()
        mock_qs.filter.return_value = filtered_qs

        result = apply_or_filters(request, mock_qs)

        mock_label_ids.assert_called_once_with([5, 6])
        mock_qs.filter.assert_called_once()
        assert result is filtered_qs

    def test_or_template_filter_applied(self):
        """Template OR filter sets template_id__in condition."""
        request = self._make_request({"or__template": [10, 20]})
        mock_qs = MagicMock()
        filtered_qs = MagicMock()
        mock_qs.filter.return_value = filtered_qs

        result = apply_or_filters(request, mock_qs)

        mock_qs.filter.assert_called_once()
        assert result is filtered_qs


@pytest.mark.unit
class TestGetFilterOptions:
    """Tests for get_filter_options function."""

    def _mock_request(self, query_params: dict[str, list[str]]) -> MagicMock:
        """Helper to create a mock request with query_params."""
        mock_request = MagicMock()
        mock_request.query_params.getlist = lambda field: query_params.get(field, [])
        return mock_request

    def test_empty_query_params(self):
        """Test with no query parameters."""
        request = self._mock_request({})
        result = get_filter_options(request)
        assert result == {}

    def test_single_organization(self):
        """Test with single organization filter."""
        request = self._mock_request({"organization": ["1"]})
        result = get_filter_options(request)
        assert result == {"organization": [1]}

    def test_multiple_organizations(self):
        """Test with multiple organization filters."""
        request = self._mock_request({"organization": ["3", "1", "2"]})
        result = get_filter_options(request)
        assert result == {"organization": [1, 2, 3]}  # Sorted

    def test_single_template(self):
        """Test with single template filter."""
        request = self._mock_request({"template": ["100"]})
        result = get_filter_options(request)
        assert result == {"template": [100]}

    def test_single_label(self):
        """Test with single label filter."""
        request = self._mock_request({"label": ["50"]})
        result = get_filter_options(request)
        assert result == {"label": [50]}

    def test_single_project(self):
        """Test with single project filter."""
        request = self._mock_request({"project": ["200"]})
        result = get_filter_options(request)
        assert result == {"project": [200]}

    def test_multiple_filter_types(self):
        """Test with multiple filter types at once."""
        request = self._mock_request(
            {
                "organization": ["1", "2"],
                "template": ["10"],
                "label": ["5", "6", "7"],
                "project": ["100"],
            }
        )
        result = get_filter_options(request)
        assert result == {
            "organization": [1, 2],
            "template": [10],
            "label": [5, 6, 7],
            "project": [100],
        }

    def test_invalid_values_filtered_out(self):
        """Test that invalid values are filtered out."""
        request = self._mock_request({"organization": ["1", "abc", "2", ""]})
        result = get_filter_options(request)
        assert result == {"organization": [1, 2]}

    def test_all_invalid_values(self):
        """Test that field is omitted when all values are invalid."""
        request = self._mock_request({"organization": ["abc", "def", ""]})
        result = get_filter_options(request)
        assert result == {}

    def test_mixed_valid_invalid_multiple_fields(self):
        """Test mixed valid/invalid values across multiple fields."""
        request = self._mock_request(
            {
                "organization": ["1", "invalid"],
                "template": ["bad", "worse"],  # All invalid
                "label": ["10", "20"],
            }
        )
        result = get_filter_options(request)
        assert result == {
            "organization": [1],
            "label": [10, 20],
        }
        assert "template" not in result  # All invalid, field omitted

    def test_duplicate_values_preserved(self):
        """Test that duplicate valid values are preserved (not deduplicated)."""
        request = self._mock_request({"organization": ["1", "1", "2"]})
        result = get_filter_options(request)
        assert result == {"organization": [1, 1, 2]}

    def test_negative_values(self):
        """Test that negative values are accepted."""
        request = self._mock_request({"organization": ["-1", "2"]})
        result = get_filter_options(request)
        assert result == {"organization": [-1, 2]}

    def test_unknown_field_ignored(self):
        """Test that unknown filter fields are ignored."""
        request = self._mock_request(
            {
                "organization": ["1"],
                "unknown_field": ["100"],
            }
        )
        result = get_filter_options(request)
        assert result == {"organization": [1]}
        assert "unknown_field" not in result

    def test_values_are_sorted(self):
        """Test that values are sorted in ascending order."""
        request = self._mock_request({"project": ["100", "5", "50", "10"]})
        result = get_filter_options(request)
        assert result == {"project": [5, 10, 50, 100]}


@pytest.mark.unit
class TestCustomReportFilter:
    """Tests for CustomReportFilter.filter_queryset method."""

    @pytest.fixture
    def filter_backend(self):
        """Create a CustomReportFilter instance."""
        return CustomReportFilter()

    @pytest.fixture
    def mock_queryset(self):
        """Create a mock queryset with chainable filter methods."""
        mock_qs = MagicMock()
        # Make all filter methods return the same mock for chaining
        mock_qs.after_date.return_value = mock_qs
        mock_qs.before_date.return_value = mock_qs
        mock_qs.organizations.return_value = mock_qs
        mock_qs.projects.return_value = mock_qs
        mock_qs.templates.return_value = mock_qs
        mock_qs.labels.return_value = mock_qs
        return mock_qs

    @pytest.fixture
    def mock_view(self):
        """Create a mock view with kwargs."""
        mock_view = MagicMock()
        mock_view.kwargs = {}
        return mock_view

    def _mock_request(self, query_params: dict[str, list[str]]) -> MagicMock:
        """Helper to create a mock request with query_params."""
        mock_request = MagicMock()
        mock_request.query_params.getlist = lambda field: query_params.get(field, [])
        # Return the first value for scalar params; fall back to the given default.
        # Required for the fallback branch in filter_queryset that reads period/tz via
        # request.query_params.get() when @require_date_range hasn't run.
        mock_request.query_params.get = lambda key, default=None: (
            query_params[key][0] if key in query_params and query_params[key] else default
        )
        return mock_request

    def test_filter_with_no_filters(self, filter_backend, mock_queryset, mock_view):
        """Test filter_queryset with no filters applied."""
        request = self._mock_request({})
        mock_view.kwargs = {}

        result = filter_backend.filter_queryset(request, mock_queryset, mock_view)

        mock_queryset.after_date.assert_called_once_with(None)
        mock_queryset.before_date.assert_called_once_with(None)
        mock_queryset.organizations.assert_called_once_with(None)
        mock_queryset.projects.assert_called_once_with(None)
        mock_queryset.templates.assert_called_once_with(None)
        mock_queryset.labels.assert_called_once_with(None)
        assert result == mock_queryset

    @patch("apps.dashboard_reports.filters.DateFilter.to_start_date_end_date")
    def test_filter_with_date_range(self, mock_to_dates, filter_backend, mock_queryset, mock_view):
        """Test filter_queryset with start_date and end_date."""
        request = self._mock_request({})
        start_date = "2024-01-01"
        end_date = "2024-12-31"
        mock_to_dates.return_value = (
            start_date,
            end_date,
        )
        mock_view.kwargs = {"period": "last_90_days", "tz": "UTC", "start_date": start_date, "end_date": end_date}

        filter_backend.filter_queryset(request, mock_queryset, mock_view)

        mock_queryset.after_date.assert_called_once_with(start_date)
        mock_queryset.before_date.assert_called_once_with(end_date)

    def test_filter_with_organization(self, filter_backend, mock_queryset, mock_view):
        """Test filter_queryset with organization filter."""
        request = self._mock_request({"organization": ["1", "2"]})
        mock_view.kwargs = {}

        filter_backend.filter_queryset(request, mock_queryset, mock_view)

        mock_queryset.organizations.assert_called_once_with([1, 2])

    def test_filter_with_template(self, filter_backend, mock_queryset, mock_view):
        """Test filter_queryset with template filter."""
        request = self._mock_request({"template": ["10", "20"]})
        mock_view.kwargs = {}

        filter_backend.filter_queryset(request, mock_queryset, mock_view)

        mock_queryset.templates.assert_called_once_with([10, 20])

    def test_filter_with_project(self, filter_backend, mock_queryset, mock_view):
        """Test filter_queryset with project filter."""
        request = self._mock_request({"project": ["100"]})
        mock_view.kwargs = {}

        filter_backend.filter_queryset(request, mock_queryset, mock_view)

        mock_queryset.projects.assert_called_once_with([100])

    def test_filter_with_label(self, filter_backend, mock_queryset, mock_view):
        """Test filter_queryset with label filter."""
        request = self._mock_request({"label": ["5", "6", "7"]})
        mock_view.kwargs = {}

        filter_backend.filter_queryset(request, mock_queryset, mock_view)

        mock_queryset.labels.assert_called_once_with([5, 6, 7])

    @patch("apps.dashboard_reports.filters.DateFilter.to_start_date_end_date")
    def test_filter_with_all_filters(self, mock_to_dates, filter_backend, mock_queryset, mock_view):
        """Test filter_queryset with all filters applied."""
        request = self._mock_request(
            {
                "organization": ["1"],
                "template": ["10"],
                "project": ["100"],
                "label": ["5"],
            }
        )
        start_date = "2024-01-01"
        end_date = "2024-06-30"
        mock_to_dates.return_value = (
            start_date,
            end_date,
        )
        mock_view.kwargs = {
            "period": "last_90_days",
            "tz": "UTC",
            "start_date": start_date,
            "end_date": end_date,
        }

        result = filter_backend.filter_queryset(request, mock_queryset, mock_view)

        mock_queryset.after_date.assert_called_once_with(start_date)
        mock_queryset.before_date.assert_called_once_with(end_date)
        mock_queryset.organizations.assert_called_once_with([1])
        mock_queryset.templates.assert_called_once_with([10])
        mock_queryset.projects.assert_called_once_with([100])
        mock_queryset.labels.assert_called_once_with([5])
        assert result == mock_queryset

    def test_filter_with_invalid_values_ignored(self, filter_backend, mock_queryset, mock_view):
        """Test filter_queryset ignores invalid filter values."""
        request = self._mock_request(
            {
                "organization": ["1", "invalid", "2"],
                "template": ["abc"],  # All invalid
            }
        )
        mock_view.kwargs = {}

        filter_backend.filter_queryset(request, mock_queryset, mock_view)

        mock_queryset.organizations.assert_called_once_with([1, 2])
        mock_queryset.templates.assert_called_once_with(None)  # All invalid, so None

    def test_filter_returns_queryset(self, filter_backend, mock_queryset, mock_view):
        """Test filter_queryset returns the filtered queryset."""
        request = self._mock_request({})
        mock_view.kwargs = {}

        result = filter_backend.filter_queryset(request, mock_queryset, mock_view)

        assert result is mock_queryset
