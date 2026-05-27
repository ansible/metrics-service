"""
Admin API for BI connector collector configuration and backfill triggering.

These endpoints are for the management UI — authenticated by session/basic auth
with IsSystemAdminOrAuditor, not the BI token scheme.

Endpoints:
    GET  /api/v1/bi/collector-settings/     — read BI_CONNECTOR_COLLECTORS setting
    PATCH /api/v1/bi/collector-settings/    — update BI_CONNECTOR_COLLECTORS setting
    GET  /api/v1/bi/collector-settings/batches/         — batch history (all collectors)
    POST /api/v1/bi/collector-settings/batches/         — trigger a backfill or on-demand run
    GET  /api/v1/bi/collector-settings/batches/<id>/    — single batch detail
"""

import json
import logging
from datetime import timedelta

from ansible_base.rbac.api.permissions import IsSystemAdminOrAuditor
from rest_framework import status
from rest_framework.mixins import CreateModelMixin, ListModelMixin, RetrieveModelMixin
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import GenericViewSet

from apps.bi_connector.models import CollectionBatch
from apps.bi_connector.v1.stored_serializers import CollectionBatchSerializer
from apps.tasks.utils import parse_datetime_string

logger = logging.getLogger(__name__)

AVAILABLE_BACKFILL_COLLECTORS = [
    # Existing hourly collectors (write to HourlyMetricsCollection via backfill_bi_collector)
    "job_host_summary_service",
    "unified_jobs",
    "credentials_service",
    "main_jobevent_service",
    # Existing snapshot collectors (write to HourlyMetricsCollection via backfill_bi_collector)
    "execution_environments",
    "config",
    "controller_version_service",
    "table_metadata",
    # New billing collectors (write to stored billing models via collect_bi_billing_data)
    "main_host",
    "main_host_daily",
    "job_host_summary",
    "main_indirectmanagednodeaudit",
]

BILLING_COLLECTORS = frozenset({"main_host", "main_host_daily", "job_host_summary", "main_indirectmanagednodeaudit"})


def _parse_and_validate_date_range(since_str, until_str):
    """Parse and validate since/until strings. Returns (since, until) or raises ValueError."""
    since = None
    until = None
    if since_str:
        since = parse_datetime_string(since_str)
        if since is None:
            raise ValueError(f"Invalid 'since' datetime: {since_str!r}. Use ISO 8601 format.")
    if until_str:
        until = parse_datetime_string(until_str)
        if until is None:
            raise ValueError(f"Invalid 'until' datetime: {until_str!r}. Use ISO 8601 format.")
    if since is not None and until is not None:
        if until <= since:
            raise ValueError("'until' must be after 'since'.")
        from django.conf import settings as django_settings

        max_backfill_days = getattr(django_settings, "BI_CONNECTOR_MAX_BACKFILL_DAYS", 365)
        if (until - since) > timedelta(days=max_backfill_days):
            raise ValueError(f"Date range cannot exceed {max_backfill_days} days.")
    return since, until


class CollectorSettingsView(APIView):
    """
    Admin view for reading and updating the BI_CONNECTOR_COLLECTORS setting.

    GET  — returns the current collector enable/disable map and available collectors list.
    PATCH — validates and persists an updated {str: bool} collector map.
    """

    permission_classes = [IsSystemAdminOrAuditor]
    versioning_class = None

    def get(self, request):
        """Return the current BI_CONNECTOR_COLLECTORS setting and available collectors."""
        from apps.dynamic_settings.models import Setting

        setting = Setting.objects.filter(setting_key="BI_CONNECTOR_COLLECTORS").first()
        current_value = None
        if setting and setting.current_value:
            try:
                current_value = json.loads(setting.current_value)
            except (json.JSONDecodeError, TypeError):
                logger.warning("BI_CONNECTOR_COLLECTORS setting contains invalid JSON; returning null.")

        return Response(
            {
                "setting_key": "BI_CONNECTOR_COLLECTORS",
                "current_value": current_value,
                "available_collectors": AVAILABLE_BACKFILL_COLLECTORS,
            }
        )

    def patch(self, request):
        """Update the BI_CONNECTOR_COLLECTORS setting.

        Expects a JSON object mapping collector name (str) to enabled flag (bool).
        Unknown keys are rejected; non-bool values are rejected.
        """
        from apps.dynamic_settings.models import Setting

        data = request.data
        if not isinstance(data, dict):
            return Response(
                {"detail": "Request body must be a JSON object mapping collector names to booleans."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        invalid_keys = [k for k in data if k not in AVAILABLE_BACKFILL_COLLECTORS]
        if invalid_keys:
            return Response(
                {"detail": f"Unknown collector(s): {invalid_keys}. Valid collectors: {AVAILABLE_BACKFILL_COLLECTORS}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        non_bool_keys = [k for k, v in data.items() if not isinstance(v, bool)]
        if non_bool_keys:
            return Response(
                {"detail": f"Values must be booleans. Non-boolean values for: {non_bool_keys}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        existing_setting = Setting.objects.filter(setting_key="BI_CONNECTOR_COLLECTORS").first()
        existing = {}
        if existing_setting and existing_setting.current_value:
            try:
                parsed = json.loads(existing_setting.current_value)
                if isinstance(parsed, dict):
                    existing = parsed
            except json.JSONDecodeError:
                pass

        merged = {**existing, **dict(data)}
        Setting.objects.update_or_create(
            setting_key="BI_CONNECTOR_COLLECTORS",
            defaults={"current_value": json.dumps(merged)},
        )

        return Response(
            {
                "setting_key": "BI_CONNECTOR_COLLECTORS",
                "current_value": merged,
                "available_collectors": AVAILABLE_BACKFILL_COLLECTORS,
            }
        )


class AdminCollectionBatchViewSet(ListModelMixin, RetrieveModelMixin, CreateModelMixin, GenericViewSet):
    """
    Admin ViewSet for CollectionBatch — list, retrieve, and trigger backfill runs.

    GET  /batches/       — list all batches, ordered by most recent first.
    GET  /batches/<id>/  — retrieve a single batch by PK.
    POST /batches/       — trigger a new backfill or on-demand collection run.

    POST body fields:
        collector_type (str, required) — must be in AVAILABLE_BACKFILL_COLLECTORS
        batch_type     (str, optional) — e.g. "backfill" or "on_demand" (default: "on_demand")
        since          (str, required for time-series collectors) — ISO 8601 datetime
        until          (str, required for time-series collectors) — ISO 8601 datetime
    """

    permission_classes = [IsSystemAdminOrAuditor]
    versioning_class = None
    queryset = CollectionBatch.objects.all().order_by("-created")
    serializer_class = CollectionBatchSerializer

    def create(self, request, *args, **kwargs):
        """Validate input, create a CollectionBatch record, and dispatch the background task."""
        from apps.tasks.models import Task
        from apps.tasks.tasks_system import submit_task_to_dispatcher

        collector_type = request.data.get("collector_type")
        if not collector_type:
            return Response(
                {"detail": "collector_type is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if collector_type not in AVAILABLE_BACKFILL_COLLECTORS:
            return Response(
                {"detail": f"Unknown collector_type '{collector_type}'. Valid values: {AVAILABLE_BACKFILL_COLLECTORS}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        since_str = request.data.get("since")
        until_str = request.data.get("until")

        # Time-series collectors require a date range; snapshot collectors do not.
        time_series_collectors = {
            "job_host_summary_service",
            "unified_jobs",
            "credentials_service",
            "main_jobevent_service",
            "main_host",
            "main_host_daily",
            "job_host_summary",
            "main_indirectmanagednodeaudit",
        }
        if collector_type in time_series_collectors:
            missing = [field for field in ("since", "until") if not request.data.get(field)]
            if missing:
                return Response(
                    {"detail": f"Fields {missing} are required for time-series collector '{collector_type}'."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        try:
            since, until = _parse_and_validate_date_range(since_str, until_str)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        _allowed_batch_types = {"scheduled", "backfill"}
        batch_type = request.data.get("batch_type", "backfill")
        if batch_type not in _allowed_batch_types:
            return Response(
                {"detail": f"Invalid batch_type '{batch_type}'. Allowed: {sorted(_allowed_batch_types)}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        batch = CollectionBatch.objects.create(
            collector_type=collector_type,
            batch_type=batch_type,
            status="pending",
            since=since,
            until=until,
        )

        # Choose the task function based on whether this is a billing collector.
        function_name = "collect_bi_billing_data" if collector_type in BILLING_COLLECTORS else "backfill_bi_collector"

        task = Task.objects.create(
            name=f"bi_backfill_{collector_type}",
            function_name=function_name,
            task_data={
                "collector_type": collector_type,
                "since": since.isoformat() if since else None,
                "until": until.isoformat() if until else None,
                "batch_id": batch.id,
            },
        )

        batch.task_id = task.id
        batch.save(update_fields=["task_id", "modified"])

        submit_task_to_dispatcher(task)

        serializer = self.get_serializer(batch)
        return Response(serializer.data, status=status.HTTP_202_ACCEPTED)
