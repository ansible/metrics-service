"""
BI connector Layer 2 views — live data queried directly from the AWX DB.

These endpoints use the existing AWX DB connection (Django "awx" alias) and
metrics_utility collector functions to serve real-time Controller data.

All time-series endpoints enforce mandatory since/until parameters with a maximum
date range to prevent unbounded queries against the production AWX DB.
Collector functions are imported lazily inside each get() method to prevent
metrics_utility import failures from breaking the entire module in test environments.
"""

import logging
from typing import Any

from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.tasks.utils import get_db_connection, parse_datetime_string

logger = logging.getLogger(__name__)


class DateRangeRequiredMixin:
    """
    Mixin that enforces mandatory since/until query parameters with a maximum window.

    Protects the AWX production DB from unbounded BI queries. Override MAX_DAYS
    on the view class to set a tighter limit (e.g., ControllerEventsView uses 3 days
    because main_jobevent is one of the largest tables in the AWX DB).
    """

    MAX_DAYS: int = 7

    def validate_date_range(self, request: Any) -> tuple:
        since_str = request.query_params.get("since")
        until_str = request.query_params.get("until")

        if not since_str or not until_str:
            raise ValidationError({"detail": "Both 'since' and 'until' query parameters are required (ISO 8601)."})

        since = parse_datetime_string(since_str)
        until = parse_datetime_string(until_str)

        if since is None:
            raise ValidationError({"detail": f"Invalid 'since' datetime format: {since_str!r}. Use ISO 8601."})
        if until is None:
            raise ValidationError({"detail": f"Invalid 'until' datetime format: {until_str!r}. Use ISO 8601."})
        if until <= since:
            raise ValidationError({"detail": "'until' must be after 'since'."})

        delta = until - since
        if delta.days > self.MAX_DAYS:
            raise ValidationError(
                {"detail": f"Date range cannot exceed {self.MAX_DAYS} days. Requested {delta.days} days."}
            )

        return since, until


class ControllerJobsView(DateRangeRequiredMixin, APIView):
    """
    Live unified jobs data from the AWX DB (max 7-day window).

    Query params:
        since (required) — start of range, ISO 8601 datetime
        until (required) — end of range, ISO 8601 datetime
    """

    permission_classes = [IsAuthenticated]
    versioning_class = None

    def get(self, request: Any) -> Response:
        since, until = self.validate_date_range(request)

        try:
            conn = get_db_connection()
        except Exception as e:
            logger.error("AWX DB unavailable for controller/jobs: %s", e)
            return Response({"error": f"AWX database unavailable: {e}"}, status=503)

        try:
            from apps.tasks.collectors.collect_hourly_metrics import _get_hourly_collectors

            collectors = _get_hourly_collectors()
            collector = collectors["unified_jobs"]["collector_func"](db=conn, since=since, until=until)
            data = collector.gather()
        except Exception as e:
            logger.error("Collection failed for controller/jobs: %s", e)
            return Response({"error": f"Collection failed: {e}"}, status=500)

        return Response({"since": since.isoformat(), "until": until.isoformat(), "collector_type": "unified_jobs", "data": data})


class ControllerHostsView(DateRangeRequiredMixin, APIView):
    """
    Live job host summary data from the AWX DB (max 7-day window).

    Query params:
        since (required) — start of range, ISO 8601 datetime
        until (required) — end of range, ISO 8601 datetime
    """

    permission_classes = [IsAuthenticated]
    versioning_class = None

    def get(self, request: Any) -> Response:
        since, until = self.validate_date_range(request)

        try:
            conn = get_db_connection()
        except Exception as e:
            logger.error("AWX DB unavailable for controller/hosts: %s", e)
            return Response({"error": f"AWX database unavailable: {e}"}, status=503)

        try:
            from apps.tasks.collectors.collect_hourly_metrics import _get_hourly_collectors

            collectors = _get_hourly_collectors()
            collector = collectors["job_host_summary_service"]["collector_func"](db=conn, since=since, until=until)
            data = collector.gather()
        except Exception as e:
            logger.error("Collection failed for controller/hosts: %s", e)
            return Response({"error": f"Collection failed: {e}"}, status=500)

        return Response(
            {"since": since.isoformat(), "until": until.isoformat(), "collector_type": "job_host_summary_service", "data": data}
        )


class ControllerCredentialsView(DateRangeRequiredMixin, APIView):
    """
    Live credentials usage data from the AWX DB (max 7-day window).

    Query params:
        since (required) — start of range, ISO 8601 datetime
        until (required) — end of range, ISO 8601 datetime
    """

    permission_classes = [IsAuthenticated]
    versioning_class = None

    def get(self, request: Any) -> Response:
        since, until = self.validate_date_range(request)

        try:
            conn = get_db_connection()
        except Exception as e:
            logger.error("AWX DB unavailable for controller/credentials: %s", e)
            return Response({"error": f"AWX database unavailable: {e}"}, status=503)

        try:
            from apps.tasks.collectors.collect_hourly_metrics import _get_hourly_collectors

            collectors = _get_hourly_collectors()
            collector = collectors["credentials_service"]["collector_func"](db=conn, since=since, until=until)
            data = collector.gather()
        except Exception as e:
            logger.error("Collection failed for controller/credentials: %s", e)
            return Response({"error": f"Collection failed: {e}"}, status=500)

        return Response(
            {"since": since.isoformat(), "until": until.isoformat(), "collector_type": "credentials_service", "data": data}
        )


class ControllerEventsView(DateRangeRequiredMixin, APIView):
    """
    Live job events (event modules) data from the AWX DB.

    Tighter 3-day max window enforced because main_jobevent is one of the
    largest tables in the AWX DB — even a 7-day query can be very heavy.

    Query params:
        since (required) — start of range, ISO 8601 datetime
        until (required) — end of range, ISO 8601 datetime
    """

    permission_classes = [IsAuthenticated]
    versioning_class = None
    MAX_DAYS: int = 3

    def get(self, request: Any) -> Response:
        since, until = self.validate_date_range(request)

        try:
            conn = get_db_connection()
        except Exception as e:
            logger.error("AWX DB unavailable for controller/events: %s", e)
            return Response({"error": f"AWX database unavailable: {e}"}, status=503)

        try:
            from apps.tasks.collectors.collect_hourly_metrics import _get_hourly_collectors

            collectors = _get_hourly_collectors()
            collector = collectors["main_jobevent_service"]["collector_func"](db=conn, since=since, until=until)
            data = collector.gather()
        except Exception as e:
            logger.error("Collection failed for controller/events: %s", e)
            return Response({"error": f"Collection failed: {e}"}, status=500)

        return Response(
            {"since": since.isoformat(), "until": until.isoformat(), "collector_type": "main_jobevent_service", "data": data}
        )


class ControllerSnapshotView(APIView):
    """
    Current-state snapshot from the AWX DB.

    Queries execution environments, controller version, table metadata, and config.
    No time window required — these are point-in-time snapshots of current state.

    Returns partial results if individual collectors fail (200 with populated errors dict).

    Optional query param:
        collectors — comma-separated subset, e.g. ?collectors=execution_environments,config
    """

    permission_classes = [IsAuthenticated]
    versioning_class = None
    DEFAULT_COLLECTORS = ["execution_environments", "controller_version_service", "table_metadata", "config"]

    def get(self, request: Any) -> Response:
        collectors_param = request.query_params.get("collectors")
        if collectors_param:
            requested = [c.strip() for c in collectors_param.split(",") if c.strip()]
        else:
            requested = self.DEFAULT_COLLECTORS

        try:
            conn = get_db_connection()
        except Exception as e:
            logger.error("AWX DB unavailable for controller/snapshot: %s", e)
            return Response({"error": f"AWX database unavailable: {e}"}, status=503)

        from apps.tasks.collectors.collect_snapshot_metrics import _get_snapshot_collectors

        registry = _get_snapshot_collectors()
        results: dict = {}
        errors: dict = {}

        for collector_type in requested:
            if collector_type not in registry:
                errors[collector_type] = f"Unknown collector type: {collector_type!r}"
                continue
            try:
                entry = registry[collector_type]
                collector = entry["collector_func"](db=conn)
                results[collector_type] = collector.gather()
            except Exception as e:
                logger.warning("Snapshot collector %s failed: %s", collector_type, e)
                errors[collector_type] = str(e)

        return Response({
            "collected_at": timezone.now().isoformat(),
            "collectors": results,
            "errors": errors,
        })
