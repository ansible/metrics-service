"""
BI connector analytics endpoints — aggregate views over HourlyMetricsCollection raw_data.

These endpoints close the gap between raw metrics-utility collection and structured
BI-consumable data by aggregating the module_stats, organizations, and duration
fields stored in HourlyMetricsCollection.raw_data.
"""

import logging
from collections import defaultdict
from typing import Any

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.tasks.models import HourlyMetricsCollection
from apps.tasks.utils import parse_datetime_string

from .mixins import BiConnectorEnabledMixin

logger = logging.getLogger(__name__)


class ModuleStatsView(BiConnectorEnabledMixin, APIView):
    """
    GET /api/v1/bi/metrics/modules/

    Aggregates module_stats from all main_jobevent_service HourlyMetricsCollection
    records. Returns per-module totals for task_runs, unique_hosts, and
    total_duration_hours (compute time).

    Closes the gap: BHP report showed module-level compute hours from CCSPv2 data.
    metrics-utility collects this in raw_data.module_stats; this endpoint surfaces it.

    Optional query params:
        since  — ISO 8601 datetime, filter collection_timestamp >= since
        until  — ISO 8601 datetime, filter collection_timestamp <= until
    """

    permission_classes = [IsAuthenticated]
    versioning_class = None

    def get(self, request: Any) -> Response:
        """Aggregate module statistics across jobevent service collections."""
        qs = HourlyMetricsCollection.objects.filter(collector_type="main_jobevent_service")

        since_str = request.query_params.get("since")
        until_str = request.query_params.get("until")
        if since_str:
            since = parse_datetime_string(since_str)
            if since:
                qs = qs.filter(collection_timestamp__gte=since)
        if until_str:
            until = parse_datetime_string(until_str)
            if until:
                qs = qs.filter(collection_timestamp__lte=until)

        module_totals: dict = defaultdict(
            lambda: {
                "module": "",
                "task_runs": 0,
                "unique_hosts": 0,
                "total_duration_hours": 0.0,
                "pct_of_total_hours": 0.0,
            }
        )
        grand_total_hours = 0.0

        for obj in qs.iterator():
            for stat in obj.raw_data.get("module_stats", []):
                mod = stat.get("module", "")
                if not mod:
                    continue
                module_totals[mod]["module"] = mod
                module_totals[mod]["task_runs"] += stat.get("task_runs", 0)
                # unique_hosts is a peak count — take max across periods
                module_totals[mod]["unique_hosts"] = max(
                    module_totals[mod]["unique_hosts"],
                    stat.get("unique_hosts", 0),
                )
                duration_hrs = stat.get("total_duration_seconds", 0) / 3600
                module_totals[mod]["total_duration_hours"] += duration_hrs
                grand_total_hours += duration_hrs

        results = sorted(module_totals.values(), key=lambda x: x["total_duration_hours"], reverse=True)

        for row in results:
            row["total_duration_hours"] = round(row["total_duration_hours"], 1)
            row["pct_of_total_hours"] = (
                round(100 * row["total_duration_hours"] / grand_total_hours, 1) if grand_total_hours else 0.0
            )

        return Response(
            {
                "total_modules": len(results),
                "total_compute_hours": round(grand_total_hours, 1),
                "total_person_work_days": round(grand_total_hours / 8, 1),
                "total_person_years": round(grand_total_hours / 8 / 240, 2),
                "results": results,
            }
        )


class OrganizationStatsView(BiConnectorEnabledMixin, APIView):
    """
    GET /api/v1/bi/metrics/organizations/

    Aggregates organization data from unified_jobs HourlyMetricsCollection
    raw_data.organizations. Returns per-org job counts and task totals.

    Closes the gap: BHP report showed org-level breakdowns from CCSPv2 data.

    Optional query params:
        since  — ISO 8601 datetime, filter collection_timestamp >= since
        until  — ISO 8601 datetime, filter collection_timestamp <= until
    """

    permission_classes = [IsAuthenticated]
    versioning_class = None

    def get(self, request: Any) -> Response:
        """Aggregate organization statistics across unified_jobs collections."""
        qs = HourlyMetricsCollection.objects.filter(collector_type="unified_jobs")

        since_str = request.query_params.get("since")
        until_str = request.query_params.get("until")
        if since_str:
            since = parse_datetime_string(since_str)
            if since:
                qs = qs.filter(collection_timestamp__gte=since)
        if until_str:
            until = parse_datetime_string(until_str)
            if until:
                qs = qs.filter(collection_timestamp__lte=until)

        org_totals: dict = defaultdict(
            lambda: {
                "org_id": None,
                "org_name": "",
                "job_count": 0,
                "task_count": 0,
            }
        )

        for obj in qs.iterator():
            for org in obj.raw_data.get("organizations", []):
                org_id = org.get("org_id")
                if org_id is None:
                    continue
                org_totals[org_id]["org_id"] = org_id
                org_totals[org_id]["org_name"] = org.get("org_name", f"Org {org_id}")
                org_totals[org_id]["job_count"] += org.get("job_count", 0)
                org_totals[org_id]["task_count"] += org.get("task_count", 0)

        results = sorted(org_totals.values(), key=lambda x: x["task_count"], reverse=True)

        return Response(
            {
                "total_organizations": len(results),
                "total_jobs": sum(r["job_count"] for r in results),
                "total_tasks": sum(r["task_count"] for r in results),
                "results": results,
            }
        )


class ComputeHoursView(BiConnectorEnabledMixin, APIView):
    """
    GET /api/v1/bi/metrics/compute-hours/

    Returns total automation compute hours derived from module_stats.total_duration_seconds
    in main_jobevent_service collections.

    Closes the gap: BHP report headline metric of 22,032 compute hours / 2,754 person-work-days.

    Optional query params:
        since  — ISO 8601 datetime, filter collection_timestamp >= since
        until  — ISO 8601 datetime, filter collection_timestamp <= until
    """

    permission_classes = [IsAuthenticated]
    versioning_class = None

    def get(self, request: Any) -> Response:
        """Return aggregate compute hours, work-days, and person-years."""
        qs = HourlyMetricsCollection.objects.filter(collector_type="main_jobevent_service")

        since_str = request.query_params.get("since")
        until_str = request.query_params.get("until")
        if since_str:
            since = parse_datetime_string(since_str)
            if since:
                qs = qs.filter(collection_timestamp__gte=since)
        if until_str:
            until = parse_datetime_string(until_str)
            if until:
                qs = qs.filter(collection_timestamp__lte=until)

        total_seconds = 0
        collection_count = 0

        for obj in qs.iterator():
            for stat in obj.raw_data.get("module_stats", []):
                total_seconds += stat.get("total_duration_seconds", 0)
            collection_count += 1

        total_hours = total_seconds / 3600
        return Response(
            {
                "collection_count": collection_count,
                "total_automation_hours": round(total_hours, 1),
                "person_work_days_8hr": round(total_hours / 8, 1),
                "person_years_240days": round(total_hours / 8 / 240, 2),
                "avg_hours_per_collection": round(total_hours / collection_count, 2) if collection_count else 0,
            }
        )
