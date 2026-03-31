import datetime
import logging
from collections.abc import Sequence
from enum import Enum

import pytz
from django.db import models
from django.db.models import QuerySet
from rest_framework import filters
from rest_framework.request import Request
from rest_framework.views import APIView

from apps.dashboard_reports.models import JobData, JobLabel

logger = logging.getLogger(__name__)


FILTER_FIELDS: dict[str, str] = {
    "organization": "organizations",
    "template": "templates",
    "label": "labels",
    "project": "projects",
}


class DateFilter(Enum):
    LAST_7_DAYS = "last_7_days"
    LAST_14_DAYS = "last_14_days"
    LAST_30_DAYS = "last_30_days"
    LAST_60_DAYS = "last_60_days"
    LAST_90_DAYS = "last_90_days"

    @classmethod
    def to_list(cls) -> Sequence[str]:
        return [v.value for v in DateFilter]

    @classmethod
    def get_num_last_days(cls, value: str) -> int | None:
        return int(value.replace("last_", "").replace("_days", "")) if value is not None else None

    @classmethod
    def to_start_date_end_date(cls, value: str, tz_string: str) -> tuple[str, str]:
        num_of_last_days = cls.get_num_last_days(value=value)
        if num_of_last_days is None:
            return None, None

        # NOTE: get start and end days
        # end_date -> current date
        # start_date -> start_date - num_of_last_days
        # return start_date, end_date

        try:
            tz = pytz.timezone(tz_string)
        except pytz.UnknownTimeZoneError as _:
            logger.exception("Error: Unknown timezone: %s, using default timezone 'UTC'", tz_string)
            tz = pytz.timezone("UTC")

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
    return {field: sorted(values) for field in FILTER_FIELDS if (values := _collect_int_params(request, field))}


def get_or_filter_options(request: Request) -> dict[str, list[int]]:
    return {
        field: sorted(values) for field in FILTER_FIELDS if (values := _collect_int_params(request, f"or__{field}"))
    }


def apply_or_filters(request: Request, queryset: QuerySet[JobData]) -> QuerySet[JobData]:
    or_options = get_or_filter_options(request=request)
    if not or_options:
        return queryset

    q = models.Q()
    for field, values in or_options.items():
        if field == "label":
            labels_qs = JobLabel.objects.filter(label_id__in=values).values_list("job_data_id", flat=True)
            q |= models.Q(id__in=labels_qs)
        elif field == "organization":
            q |= models.Q(organization_id__in=values)
        elif field == "template":
            q |= models.Q(template_id__in=values)
        elif field == "project":
            q |= models.Q(project_id__in=values)

    return queryset.filter(q)


def _collect_int_params(request: Request, key: str) -> list[int]:
    return [v for value in request.query_params.getlist(key) if (v := _safe_int(value)) is not None]


class CustomReportFilter(filters.BaseFilterBackend):
    def filter_queryset(self, request: Request, queryset: QuerySet[JobData], view: APIView) -> QuerySet[JobData]:
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
