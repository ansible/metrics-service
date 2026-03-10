import decimal
import logging
from datetime import UTC, datetime
from functools import wraps
from typing import Any

from django.db import models
from django.db.models import Count, F, OuterRef, Q, QuerySet, Subquery, Sum, Value
from django.db.models.functions import Coalesce, Trunc
from django_generate_series.models import generate_series
from rest_framework import filters, status
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.viewsets import ReadOnlyModelViewSet

from apps.core.permissions import DeveloperModeRequired
from apps.dashboard_reports.filters import CustomReportFilter, get_filter_options
from apps.dashboard_reports.models import JobData, JobHostSummary, JobStatusChoices, SubscriptionCost
from apps.dashboard_reports.serializers import (
    ReportDetailSerializer,
    ReportSerializer,
)
from apps.tasks.api_utils import build_error_response

logger = logging.getLogger(__name__)


def parse_date_param(date_str: str | None, param_name: str) -> tuple[datetime | None, str]:
    """
    Validates ISO date string for query parameters.
    """
    if not date_str:
        msg = f"{param_name} is required"
        logger.error(msg)
        return None, msg
    try:
        result = datetime.fromisoformat(date_str)
        return result, ""
    except ValueError as e:
        msg = f"Invalid {param_name} format: {date_str}. Error: {str(e)}"
        logger.error(msg)
        return None, msg


def require_date_range(view_func):
    @wraps(view_func)
    def wrapper(view, *args, **kwargs) -> Response:
        # Use request.GET for query parameters (works for DRF and Django)
        start_date_str = view.request.GET.get("start_date", None)
        end_date_str = view.request.GET.get("end_date", None)

        start_date, start_date_err_msg = parse_date_param(start_date_str, "start_date")
        if not start_date:
            error_response = build_error_response(start_date_err_msg, status_code=400)
            return Response(error_response, status=status.HTTP_400_BAD_REQUEST)

        end_date, end_date_err_msg = parse_date_param(end_date_str, "end_date")

        if not end_date:
            error_response = build_error_response(end_date_err_msg, status_code=400)
            return Response(error_response, status=status.HTTP_400_BAD_REQUEST)

        # Inject parsed dates into kwargs for downstream use
        view.kwargs["start_date"] = start_date
        view.kwargs["end_date"] = end_date

        return view_func(view, *args, **kwargs)

    return wrapper


class DashboardReportViewSet(ReadOnlyModelViewSet):
    """
    ViewSet for dashboard reporting and chart data aggregation.
    Provides endpoints for report data, summary, chart, and top users/projects.

    Endpoints:
        GET /api/v1/dashboard_reports/report/ - List all data (paginated)
        GET /api/v1/dashboard_reports/report/details/ - Get  report summary, chart data, and top users/projects

    Query Parameters:
        page (int): Page number (default: 1)
        page_size (int): Results per page (default: 10)
        start_date (iso date time string): Filter for report start date (required)
        end_date (iso date time string): Filter for report end date (required)
        organization (int): Filter by organization ID (multiple allowed)
        template (int): Filter by job template ID (multiple allowed)
        label (int): Filter by label ID (multiple allowed)
        project (int): Filter by project ID (multiple allowed)
        ordering (str): Field to order by (e.g. "template_name", "successful_runs", "savings", etc.)

    """

    versioning_class = None  # Disable versioning for this viewset
    permission_classes = [DeveloperModeRequired]
    serializer_class = ReportSerializer

    filter_backends = [CustomReportFilter, filters.OrderingFilter]

    # Maximum number of top users/projects to return in details endpoint
    TOP_RESULTS_LIMIT = 5

    ordering_fields: list[str] = [
        "template_name",
        "successful_runs",
        "failed_runs",
        "num_hosts",
        "elapsed",
        "manual_time",
        "manual_costs",
        "automated_costs",
        "savings",
        "runs",
    ]

    ordering = ["template_name"]

    def get_serializer_class(self) -> type:
        if self.action == "details":
            return ReportDetailSerializer
        return super().get_serializer_class()

    def get_queryset(self) -> QuerySet[JobData]:
        """
        Builds annotated queryset for dashboard reporting, including cost and time calculations.
        """

        subscription_cost = SubscriptionCost.get()
        average_cost_employee_minute = subscription_cost.cost_employee_per_minute
        start_date = self.kwargs.get("start_date", None)
        end_date = self.kwargs.get("end_date", None)

        aap_subscription_per_second = subscription_cost.per_second_subscription_cost(start_date, end_date)
        enable_template_creation_time = subscription_cost.include_template_creation_time_in_costs

        if enable_template_creation_time:
            automated_costs = (F("time_taken_create_automation_minutes") * average_cost_employee_minute) + (
                F("elapsed") * aap_subscription_per_second
            )
            time_savings = (
                F("manual_time") - F("elapsed") - (F("time_taken_create_automation_minutes") * decimal.Decimal(60))
            )
        else:
            automated_costs = F("elapsed") * aap_subscription_per_second
            time_savings = F("manual_time") - F("elapsed")

        manual_costs = F("num_hosts") * F("time_taken_manually_execute_minutes") * average_cost_employee_minute
        manual_time = F("num_hosts") * (F("time_taken_manually_execute_minutes") * 60)

        qs = (
            JobData.objects.prefetch_related("template_metadata")
            .values(
                "template_name",
                "template_metadata_id",
                time_taken_manually_execute_minutes=F("template_metadata__time_taken_manually_execute_minutes"),
                time_taken_create_automation_minutes=F("template_metadata__time_taken_create_automation_minutes"),
            )
            .annotate(
                runs=Count("id"),
                successful_runs=Count("id", filter=Q(status=JobStatusChoices.SUCCESSFUL)),
                failed_runs=Count("id", filter=Q(status=JobStatusChoices.FAILED)),
                elapsed=Sum("elapsed"),
                num_hosts=Sum("num_hosts"),
                automated_costs=automated_costs,
                manual_costs=manual_costs,
                manual_time=manual_time,
                time_savings=time_savings,
                savings=(F("manual_costs") - F("automated_costs")),
            )
        )
        return qs

    @require_date_range
    def list(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """
        Returns paginated report data for dashboard.
        """
        return super().list(request, *args, **kwargs)

    def _get_date_range_and_kind(self) -> tuple[datetime | None, datetime | None, str | None]:
        start_date = self.kwargs.get("start_date", None)
        end_date = self.kwargs.get("end_date", None)

        if start_date is None or end_date is None:
            return None, None, None

        start_date = start_date.astimezone(UTC)
        end_date = end_date.astimezone(UTC)

        diff = abs(end_date - start_date)
        # Trigger 'year' kind for any range spanning different years
        if start_date.year != end_date.year:
            kind = "year"
            start_date = start_date.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
            end_date = end_date.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        elif diff.days <= 1:
            kind = "hour"
            start_date = start_date.replace(minute=0, second=0, microsecond=0)
            end_date = end_date.replace(minute=0, second=0, microsecond=0)
        elif diff.days <= 45:
            kind = "day"
            start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
            end_date = end_date.replace(hour=0, minute=0, second=0, microsecond=0)
        else:
            kind = "month"
            start_date = start_date.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            end_date = end_date.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        return start_date, end_date, kind

    def _prepare_chart_querysets(self, kind: str) -> tuple[QuerySet, QuerySet]:
        """
        Prepares job and host chart querysets for the given kind.
        Returns: (job_chart_qs, host_chart_qs)
        """
        qs = self.filter_queryset(JobData.objects.all())
        qs = qs.values(date=Trunc(expression="finished", kind=kind, output_field=models.DateTimeField())).filter(
            date=OuterRef("term")
        )
        job_chart_qs = qs.annotate(runs=Count("id")).values("runs").order_by()
        host_chart_qs = qs.annotate(num_hosts=Sum("num_hosts")).values("num_hosts").order_by()
        return job_chart_qs, host_chart_qs

    def _format_chart_result(self, date_sequence_queryset: QuerySet) -> dict[str, Any]:
        """
        Formats the chart result from the date sequence queryset.
        Returns: dict with host_chart and job_chart.
        """
        result = {"host_chart": {"kind": "", "items": []}, "job_chart": {"kind": "", "items": []}}
        for row in date_sequence_queryset:
            result["job_chart"]["items"].append({"label": row.term, "value": row.runs})
            result["host_chart"]["items"].append({"label": row.term, "value": row.hosts})
        return result

    def get_chart_data(self) -> dict[str, Any]:
        """
        Returns chart data for jobs and hosts over a time range, grouped by kind (hour, day, month, year).
        """
        start_date, end_date, kind = self._get_date_range_and_kind()
        if not start_date or not end_date or not kind:
            return {"host_chart": {"kind": "", "items": []}, "job_chart": {"kind": "", "items": []}}

        job_chart_qs, host_chart_qs = self._prepare_chart_querysets(kind)

        # Generate a time series from start_date to end_date using PostgreSQL's generate_series function.
        # - start/stop: Define the date range boundaries
        # - step: Interval between each point (e.g., "1 hours", "1 days", "1 months", "1 years")
        # - span: Number of intervals to include beyond the stop date (buffer for edge cases)
        # - output_field: Ensures the series generates DateTimeField values
        # The resulting queryset contains a 'term' column with each timestamp in the series.
        date_sequence_queryset = generate_series(
            start=start_date, stop=end_date, step=f"1 {kind}s", span=5, output_field=models.DateTimeField
        ).annotate(
            # For each time point in the series, fetch the count of job runs (or 0 if none)
            runs=Coalesce(Subquery(job_chart_qs), Value(0)),
            # For each time point in the series, fetch the sum of hosts (or 0 if none)
            hosts=Coalesce(Subquery(host_chart_qs), Value(0)),
        )

        result = self._format_chart_result(date_sequence_queryset)
        result["host_chart"]["kind"] = kind
        result["job_chart"]["kind"] = kind
        return result

    @action(detail=False, methods=["get"], url_path="details")
    @require_date_range
    def details(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """
        Returns summary, chart data, and top users/projects for dashboard.
         - Summary includes total runs, successful runs, failed runs, total time savings, and total cost savings.
         - Chart data provides aggregated metrics by job template for visualizations.
         - Top users and projects identify the most active users and projects in the given date range.
         All data is filtered by the provided date range and any additional filters (organization, template, label, project).
        """

        filtered_qs = self.filter_queryset(JobData.objects.all())

        ### TOP USERS ###
        top_users_qs = (
            filtered_qs.filter(launched_by_id__isnull=False)
            .values("launched_by_id", "launched_by_username")
            .annotate(count=Count("id"))
            .order_by("-count", "launched_by_id")[: self.TOP_RESULTS_LIMIT]
        )

        ### TOP PROJECTS ###
        top_projects_qs = (
            filtered_qs.filter(project_id__isnull=False)
            .values("project_id", "project_name")
            .annotate(count=Count("id"))
            .order_by("-count", "project_id")[: self.TOP_RESULTS_LIMIT]
        )

        ### AGGREGATED DATA ###
        query_set = self.get_queryset()
        qs = self.filter_queryset(query_set)
        report_data_qs = qs.aggregate(
            total_runs=Sum("runs"),
            total_successful_runs=Sum("successful_runs"),
            total_failed_runs=Sum("failed_runs"),
            total_num_hosts=Sum("num_hosts"),
            total_elapsed=Sum("elapsed"),
            total_manual_time=Sum("manual_time"),
            total_manual_costs=Sum("manual_costs"),
            total_automated_costs=Sum("automated_costs"),
            total_savings=Sum("savings"),
            total_time_savings=Sum("time_savings"),
        )

        options = get_filter_options(request=request)

        start_date = self.kwargs.get("start_date")
        end_date = self.kwargs.get("end_date")

        ### Unique hosts count ###
        unique_hosts_count = JobHostSummary.unique_count(start_date, end_date, options)

        ### CHART DATA ###
        chart_data = self.get_chart_data()

        ### Serialize data ###
        report_data = self.get_serializer(
            {
                **report_data_qs,
                "top_users": top_users_qs,
                "top_projects": top_projects_qs,
                "total_number_of_unique_hosts": unique_hosts_count,
                **chart_data,
            }
        ).data

        return Response(report_data, status=status.HTTP_200_OK)
