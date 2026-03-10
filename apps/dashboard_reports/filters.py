from django.db.models import QuerySet
from rest_framework import filters
from rest_framework.request import Request
from rest_framework.views import APIView

from apps.dashboard_reports.models import JobData


def _safe_int(value: str) -> int | None:
    """Safely convert a string to int, returning None if conversion fails."""
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def get_filter_options(request: Request) -> dict[str, list[int]]:
    filter_fields = [
        "organization",
        "template",
        "label",
        "project",
    ]
    filter_options = {}
    for field in filter_fields:
        int_values = [v for value in request.query_params.getlist(field) if (v := _safe_int(value)) is not None]
        if int_values:
            filter_options[field] = sorted(int_values)

    return filter_options


class CustomReportFilter(filters.BaseFilterBackend):
    def filter_queryset(self, request: Request, queryset: QuerySet[JobData], view: APIView) -> QuerySet[JobData]:
        start_date = view.kwargs.get("start_date", None)
        end_date = view.kwargs.get("end_date", None)
        queryset = queryset.after_date(start_date)
        queryset = queryset.before_date(end_date)

        filter_options = get_filter_options(request)
        queryset = queryset.organizations(filter_options.get("organization", None))
        queryset = queryset.projects(filter_options.get("project", None))
        queryset = queryset.templates(filter_options.get("template", None))
        queryset = queryset.labels(filter_options.get("label", None))
        return queryset
