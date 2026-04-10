"""
Filter utilities for dashboard reports.

Provides date range filtering via DateFilter enum, AND/OR filter helpers for
organization, template, project and label query parameters, and the
CustomReportFilter backend used by DashboardReportViewSet.
"""

import datetime
import logging
from collections.abc import Sequence
from enum import Enum
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.db import models
from django.db.models import QuerySet
from rest_framework import filters
from rest_framework.request import Request
from rest_framework.views import APIView

from apps.dashboard_reports.models import JobData, label_ids_to_job_data_ids

logger = logging.getLogger(__name__)


FILTER_FIELDS: frozenset[str] = frozenset({"organization", "template", "label", "project"})


class DateFilter(Enum):
    """Enumeration of supported relative date range filter values for dashboard reports."""

    LAST_7_DAYS = "last_7_days"
    LAST_14_DAYS = "last_14_days"
    LAST_30_DAYS = "last_30_days"
    LAST_60_DAYS = "last_60_days"
    LAST_90_DAYS = "last_90_days"

    @classmethod
    def to_list(cls) -> Sequence[str]:
        """Return a list of all valid date filter string values."""
        return [v.value for v in DateFilter]

    @classmethod
    def get_num_last_days(cls, value: str) -> int | None:
        """Extract the number of days from a DateFilter value string (e.g. 'last_30_days' → 30)."""
        return int(value.replace("last_", "").replace("_days", "")) if value is not None else None

    @classmethod
    def to_start_date_end_date(cls, value: str, tz_string: str) -> tuple[str, str]:
        """
        Convert a DateFilter string to a (start_date, end_date) tuple for the given timezone.

        Returns (None, None) if the value cannot be parsed.
        """
        num_of_last_days = cls.get_num_last_days(value=value)
        if num_of_last_days is None:
            return None, None

        # NOTE: get start and end days
        # end_date -> current date
        # start_date -> start_date - num_of_last_days
        # return start_date, end_date

        try:
            tz = ZoneInfo(tz_string)
        except ZoneInfoNotFoundError:
            logger.warning("Unknown timezone provided, falling back to UTC")
            tz = ZoneInfo("UTC")

        end_date = datetime.datetime.now(tz)  # current date
        start_date = end_date - datetime.timedelta(num_of_last_days)  # current date - last_n_days

        return start_date, end_date


def _safe_int(value: str) -> int | None:
    """Safely convert a string to int, returning None if conversion fails."""
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def get_filter_options(request: Request) -> dict[str, list[int]]:
    """Return AND filter options parsed from request query parameters as {field: [int, ...]}."""
    return {field: sorted(values) for field in FILTER_FIELDS if (values := _collect_int_params(request, field))}


def get_or_filter_options(request: Request) -> dict[str, list[int]]:
    """Return OR filter options parsed from or__<field> request query parameters as {field: [int, ...]}."""
    return {
        field: sorted(values) for field in FILTER_FIELDS if (values := _collect_int_params(request, f"or__{field}"))
    }


def apply_or_filters(request: Request, queryset: QuerySet[JobData]) -> QuerySet[JobData]:
    """Apply OR-combined filter conditions from or__<field> query params to the queryset."""
    or_options = get_or_filter_options(request=request)
    if not or_options:
        return queryset

    q = models.Q()
    for field, values in or_options.items():
        if field == "label":
            q |= models.Q(id__in=label_ids_to_job_data_ids(values))
        elif field == "organization":
            q |= models.Q(organization_id__in=values)
        elif field == "template":
            q |= models.Q(template_id__in=values)
        elif field == "project":
            q |= models.Q(project_id__in=values)

    return queryset.filter(q)


def _collect_int_params(request: Request, key: str) -> list[int]:
    """Collect all integer values for a given query parameter key, skipping non-integer values."""
    return [v for value in request.query_params.getlist(key) if (v := _safe_int(value)) is not None]


class CustomReportFilter(filters.BaseFilterBackend):
    """DRF filter backend that applies date range and AND/OR filters to a JobData queryset."""

    def filter_queryset(self, request: Request, queryset: QuerySet[JobData], view: APIView) -> QuerySet[JobData]:
        """
        Apply date range and AND/OR field filters from the request to the JobData queryset.

        Reads start_date/end_date from view.kwargs (injected by @require_date_range) and
        falls back to parsing the period/tz query params directly if not present.
        """
        # Reuse the already-parsed window injected by @require_date_range to avoid
        # calling now() a second time and potentially shifting the window mid-request.
        start_date = view.kwargs.get("start_date")
        end_date = view.kwargs.get("end_date")
        if start_date is None or end_date is None:
            period = view.kwargs.get("period", None)
            tz = view.kwargs.get("tz", "UTC") or "UTC"
            start_date, end_date = DateFilter.to_start_date_end_date(value=period, tz_string=tz)

        queryset = queryset.after_date(start_date)
        queryset = queryset.before_date(end_date)

        # AND filters
        filter_options = get_filter_options(request)
        queryset = queryset.organizations(filter_options.get("organization", None))
        queryset = queryset.projects(filter_options.get("project", None))
        queryset = queryset.templates(filter_options.get("template", None))
        queryset = queryset.labels(filter_options.get("label", None))

        # OR filters
        queryset = apply_or_filters(request=request, queryset=queryset)

        return queryset
