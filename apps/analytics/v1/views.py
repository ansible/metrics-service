"""Analytics API views (ANSTRAT-1587 / AAP-87799)."""

from __future__ import annotations

from datetime import UTC, timedelta
from types import SimpleNamespace
from uuid import uuid4

from ansible_base.rbac.api.permissions import IsSystemAdminOrAuditor
from ansible_base.rest_pagination import DefaultPaginator
from django.conf import settings
from django.db import connection, transaction
from django.db.models import Max, Q
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiExample, OpenApiParameter, extend_schema, inline_serializer
from rest_framework import generics, status
from rest_framework import serializers as drf_serializers
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.reverse import reverse
from rest_framework.views import APIView

from apps.analytics.models import AnalyticsPayload
from apps.analytics.registry import enabled_collectors, get_entry
from apps.analytics.v1.serializers import (
    AnalyticsPayloadSerializer,
    CollectorDiscoverySerializer,
    analytics_payload_page_serializer,
)
from apps.core.url_prefix import replace_api_root
from apps.tasks.models import Task, TaskExecution

_ANALYTICS_ROW_FIELDS_DESCRIPTION = """The linked collector row endpoints return paginated collection envelopes. Each row contains:

- `id`: unique stored collection row identifier.
- `collector`: public `group.function` collector name.
- `source`: originating platform component, normally `local`.
- `cluster_id`: Controller installation UUID (`INSTALL_UUID`), or null if unavailable.
- `since`: inclusive start bound passed to the collector, or null for an open bound or snapshot.
- `until`: exclusive end bound passed to the collector, or null for an open bound or snapshot.
- `started_at`: timestamp when collection started.
- `finished_at`: timestamp when collection finished.
- `payload`: raw JSON output from the collector before rollup preparation. Its schema is selected
  by `collector`; the discovery response and OpenAPI components identify every enabled collector's
  fields and types.
"""

_ANALYTICS_ROOT_DESCRIPTION = """List the collectors the analytics API exposes (discovery entry point).

Response fields:

- `collectors`: list of enabled collector descriptions.
- `name`: public `group.function` collector name.
- `description`: summary of the collector's output.
- `payload_shape`: top-level JSON shape of `payload`, either `object` or `array`.
- `key_field`: field represented by top-level object keys, or null when the payload is an array or
  the object has fixed keys.
- `mode`: `hourly`, `daily`, or `snapshot`.
- `accepts_since_until`: whether collection windows are supported.
- `last_collect`: timestamp when the latest successful collection finished, or null if it has not
  been collected.
- `rows_url`: URL for stored collection envelopes.
- `collect_url`: URL for triggering an on-demand collection task.
"""

_ANALYTICS_PAGINATION_PARAMETERS = [
    OpenApiParameter(
        name="page",
        type=OpenApiTypes.INT,
        location=OpenApiParameter.QUERY,
        description="A page number within the paginated result set.",
    ),
    OpenApiParameter(
        name="page_size",
        type=OpenApiTypes.INT,
        location=OpenApiParameter.QUERY,
        description="Number of results to return per page.",
    ),
]


def _parse_dt(value):
    """Parse an ISO datetime value from a query param / request body.

    Returns None when no value was given, the parsed datetime on success, or False when the
    value is present but malformed (so callers can distinguish "absent" from "invalid").
    """
    if not value:
        return None
    from django.utils.dateparse import parse_datetime

    try:
        parsed = parse_datetime(value)
    except (ValueError, TypeError):
        return False
    if parsed is None:
        return False
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, UTC)
    return parsed


def _default_window(mode, now):
    """Return the default collection window for an hourly or daily collector."""
    if mode == "hourly":
        floor = now.replace(minute=0, second=0, microsecond=0)
        return floor - timedelta(hours=1), floor
    if mode == "daily":
        midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return midnight - timedelta(days=1), midnight
    return None, None


COLLECT_FUNCTION = "collect_analytics_on_demand"
_STALE_ERROR = "Task timed out — worker died before completion"

_COLLECT_RESPONSE_FIELDS = {
    "task_id": drf_serializers.IntegerField(),
    "task_url": drf_serializers.URLField(),
    "collector": drf_serializers.CharField(),
    "task_data": drf_serializers.DictField(),
    "task_status": drf_serializers.CharField(help_text="Current Task status."),
    "disposition": drf_serializers.ChoiceField(
        choices=("created", "reused", "requeued"),
        help_text="Whether this request created a task, reused an existing one, or requeued a failed/stale one.",
    ),
}


_COLLECT_RESPONSE = inline_serializer(name="AnalyticsCollectResponse", fields=_COLLECT_RESPONSE_FIELDS)


def _task_key(collector, since, until):
    """Return the canonical task_data that identifies one collection request."""
    key = {"collector": collector}
    if since is not None:
        key["since"] = since.isoformat()
    if until is not None:
        key["until"] = until.isoformat()
    return key


def _fail_stale(task, now):
    """Fail a stuck running task the way the scheduler does, then requeue it."""
    with transaction.atomic():
        TaskExecution.objects.filter(task=task, status="running").update(
            status="failed", error_message=_STALE_ERROR, completed_at=now
        )
        Task.objects.filter(pk=task.pk, status="running").update(
            status="failed", error_message=_STALE_ERROR, completed_at=now
        )
    return task.retry(force=True)


def _collector_discovery_example() -> dict[str, list[dict[str, object]]]:
    """Build the OpenAPI example from the enabled collector registry."""
    return {
        "collectors": [
            {
                "name": entry.name,
                "description": entry.description,
                "payload_shape": entry.payload_shape,
                "key_field": entry.key_field,
                "mode": entry.mode,
                "accepts_since_until": entry.accepts_since_until,
                "last_collect": None,
                "rows_url": replace_api_root(
                    f"https://metrics.example.com/api/v1/analytics/{entry.name}/",
                    settings.URL_PREFIX,
                ),
                "collect_url": replace_api_root(
                    f"https://metrics.example.com/api/v1/analytics/{entry.name}/collect/",
                    settings.URL_PREFIX,
                ),
            }
            for entry in enabled_collectors().values()
        ]
    }


class AnalyticsPaginator(DefaultPaginator):
    """Use absolute navigation URLs while retaining the DAB pagination options."""

    def get_next_link(self) -> str | None:
        """Return an absolute URL for the next page, when present."""
        return PageNumberPagination.get_next_link(self)

    def get_previous_link(self) -> str | None:
        """Return an absolute URL for the previous page, when present."""
        return PageNumberPagination.get_previous_link(self)


class AnalyticsRootView(APIView):
    __doc__ = _ANALYTICS_ROOT_DESCRIPTION

    permission_classes = [IsSystemAdminOrAuditor]

    @extend_schema(
        summary="Discover enabled analytics collectors.",
        description=_ANALYTICS_ROOT_DESCRIPTION,
        responses={
            200: inline_serializer(
                name="AnalyticsRootResponse",
                fields={"collectors": CollectorDiscoverySerializer(many=True)},
            )
        },
        examples=[
            OpenApiExample(
                name="Enabled analytics collectors",
                value=_collector_discovery_example(),
                response_only=True,
            )
        ],
    )
    def get(self, request, *args, **kwargs):
        """Return the enabled collectors, descriptions, and their rows URLs."""
        entries = list(enabled_collectors().values())
        last_collect_by_collector = dict(
            AnalyticsPayload.objects.filter(collector__in=[entry.name for entry in entries])
            .values("collector")
            .annotate(last_collect=Max("finished_at"))
            .values_list("collector", "last_collect")
        )
        collectors = [
            SimpleNamespace(
                name=entry.name,
                description=entry.description,
                payload_shape=entry.payload_shape,
                key_field=entry.key_field,
                mode=entry.mode,
                accepts_since_until=entry.accepts_since_until,
                last_collect=last_collect_by_collector.get(entry.name),
            )
            for entry in entries
        ]
        serializer = CollectorDiscoverySerializer(
            collectors,
            many=True,
            context={"request": request},
        )
        return Response({"collectors": serializer.data})


class CollectorRowsView(generics.GenericAPIView):
    __doc__ = _ANALYTICS_ROW_FIELDS_DESCRIPTION

    permission_classes = [IsSystemAdminOrAuditor]
    serializer_class = AnalyticsPayloadSerializer
    pagination_class = AnalyticsPaginator
    # Disable the DAB field-lookup/filter backends: they would treat ``since``/``until`` as
    # exact-match field lookups on the model and override our window-*overlap* semantics. We keep
    # DAB pagination but own the filtering here.
    filter_backends: list = []

    @extend_schema(
        description=_ANALYTICS_ROW_FIELDS_DESCRIPTION,
        responses=analytics_payload_page_serializer(),
        parameters=_ANALYTICS_PAGINATION_PARAMETERS
        + [
            OpenApiParameter(
                name="since",
                type=OpenApiTypes.DATETIME,
                location=OpenApiParameter.QUERY,
                description="Return rows whose collection window overlaps this inclusive bound.",
            ),
            OpenApiParameter(
                name="until",
                type=OpenApiTypes.DATETIME,
                location=OpenApiParameter.QUERY,
                description="Return rows whose collection window overlaps this exclusive bound.",
            ),
        ],
    )
    def get(self, request, *args, **kwargs):
        """Return paginated payloads for the requested collector."""
        return self.list(request, *args, **kwargs)

    def get_queryset(self):
        """Filter stored payloads for the collector by since/until *window overlap*.

        A row matches when its stored ``[since, until)`` overlaps the query window (``until``
        exclusive). A null bound is treated as open-ended.
        """
        collector = self.kwargs["collector"]
        qs = AnalyticsPayload.objects.filter(collector=collector)

        parsed_since = _parse_dt(self.request.query_params.get("since"))
        parsed_until = _parse_dt(self.request.query_params.get("until"))
        # Overlap: row.until > q_since AND row.since < q_until (null bounds = open-ended = match).
        if parsed_since:
            qs = qs.filter(Q(until__isnull=True) | Q(until__gt=parsed_since))
        if parsed_until:
            qs = qs.filter(Q(since__isnull=True) | Q(since__lt=parsed_until))
        return qs.order_by("-started_at", "-id")

    def list(self, request, *args, **kwargs):
        """Reject unknown/disabled collectors and invalid query windows up front."""
        entry = get_entry(self.kwargs["collector"])
        if entry is None or not entry.enabled:
            return Response(
                {"detail": f"Unknown or disabled collector: {self.kwargs['collector']}"},
                status=status.HTTP_404_NOT_FOUND,
            )
        since = _parse_dt(request.query_params.get("since"))
        until = _parse_dt(request.query_params.get("until"))
        for param, value in (("since", since), ("until", until)):
            if value is False:
                return Response(
                    {"detail": f"Invalid {param}: {request.query_params.get(param)}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        if since is not None and until is not None and until <= since:
            return Response(
                {"detail": "until must be after since"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)


class CollectorCollectView(APIView):
    """Create or reuse one on-demand collection task for an enabled collector."""

    # Collection triggers are intentionally admin-only for now; auditor-trigger support will be
    # addressed separately, potentially through a future read-style trigger endpoint.
    permission_classes = [IsSystemAdminOrAuditor]

    def _resolve_window(self, entry, request, now):
        """Parse request bounds, apply mode defaults, and return a UTC task window or an error."""
        raw_since = request.data.get("since")
        raw_until = request.data.get("until")
        since = _parse_dt(raw_since)
        until = _parse_dt(raw_until)

        for param, value in (("since", since), ("until", until)):
            if value is False:
                return None, Response(
                    {"detail": f"Invalid {param}: {request.data.get(param)}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # Canonical UTC bounds make the task_data idempotency key independent of the offset the
        # caller used to express the same instant.
        since = since.astimezone(UTC) if since else None
        until = until.astimezone(UTC) if until else None

        if not entry.accepts_since_until:
            if since is not None or until is not None:
                return None, Response(
                    {"detail": f"Collector {entry.name} is snapshot-only and does not accept since/until"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            return (None, None), None

        default_since, default_until = _default_window(entry.mode, now)
        if "since" not in request.data:
            since = default_since
        if "until" not in request.data:
            until = default_until
        if since is not None and until is not None and until <= since:
            return None, Response(
                {"detail": "until must be after since"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return (since, until), None

    def _response(self, request, task, disposition):
        """Build the shared task envelope; reused work answers 200, anything else 202."""
        task_url = reverse("tasks:v1:task-detail", kwargs={"pk": task.pk}, request=request)
        response = Response(
            {
                "task_id": task.pk,
                "task_url": task_url,
                "collector": task.task_data["collector"],
                "task_data": task.task_data,
                "task_status": task.status,
                "disposition": disposition,
            },
            status=status.HTTP_200_OK if disposition == "reused" else status.HTTP_202_ACCEPTED,
        )
        response["Location"] = task_url
        return response

    def _exact_task(self, key):
        """Return the newest task whose task_data is exactly this collector and window."""
        return Task.objects.filter(function_name=COLLECT_FUNCTION, task_data=key).order_by("-id").first()

    def _blocking_task(self, collector):
        """Return a live task for a different window of the same collector."""
        return (
            Task.objects.filter(
                function_name=COLLECT_FUNCTION,
                task_data__contains={"collector": collector},
                status__in=("pending", "running"),
            )
            .order_by("-id")
            .first()
        )

    def _settle(self, request, task, now):
        """Reuse an existing task, recovering it first when it is failed or stuck."""
        if (
            task.status == "running"
            and task.started_at
            and task.started_at < now - timedelta(seconds=settings.TASK_TIMEOUT)
        ):
            if _fail_stale(task, now):
                return self._response(request, task, "requeued")
            task.refresh_from_db()
        if task.status == "failed":
            if task.retry(force=True):
                return self._response(request, task, "requeued")
            task.refresh_from_db()
        return self._response(request, task, "reused")

    def _entry(self, collector):
        """Return the registry entry, or an error response for an unknown or disabled collector."""
        entry = get_entry(collector)
        if entry is None:
            return None, Response({"detail": f"Unknown collector: {collector}"}, status=status.HTTP_404_NOT_FOUND)
        if not entry.enabled:
            return None, Response({"detail": f"Collector is disabled: {collector}"}, status=status.HTTP_410_GONE)
        return entry, None

    @extend_schema(
        summary="Trigger an on-demand collection.",
        description=(
            "Create one task for the collector and resolved window, or reuse the task already "
            "covering that window. An identical repeat returns the same `task_id` with "
            "`disposition=reused` (200); a failed or stale task is requeued (202, `requeued`). "
            "A different pending or running window for the same collector returns 409."
        ),
        request=inline_serializer(
            name="AnalyticsCollectRequest",
            fields={
                "since": drf_serializers.DateTimeField(
                    required=False,
                    allow_null=True,
                    help_text="Collection start; omitted values use the mode default.",
                ),
                "until": drf_serializers.DateTimeField(
                    required=False,
                    allow_null=True,
                    help_text="Collection end; omitted values use the mode default.",
                ),
            },
        ),
        responses={
            200: _COLLECT_RESPONSE,
            202: _COLLECT_RESPONSE,
            409: inline_serializer(
                name="AnalyticsCollectConflict",
                fields={
                    "detail": drf_serializers.CharField(),
                    "task_id": drf_serializers.IntegerField(),
                    "task_url": drf_serializers.URLField(),
                    "task_status": drf_serializers.CharField(),
                    "task_data": drf_serializers.DictField(),
                },
            ),
        },
    )
    def post(self, request, *args, **kwargs):
        """Create, reuse, or requeue the task for this collector and window."""
        collector = self.kwargs["collector"]
        entry, error = self._entry(collector)
        if error is not None:
            return error

        if "source" in request.data:
            return Response(
                {"detail": "source is not configurable for collection tasks"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            # Serialise read-then-create per collector; released automatically on commit/rollback.
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_xact_lock(hashtext(%s)::bigint)", [f"analytics:collect:{collector}"])

            now = timezone.now()
            window, error = self._resolve_window(entry, request, now)
            if error is not None:
                return error
            task_data = _task_key(collector, *window)

            task = self._exact_task(task_data)
            if task is not None and task.status != "cancelled":
                return self._settle(request, task, now)

            blocking = self._blocking_task(collector)
            if blocking is not None:
                task_url = reverse("tasks:v1:task-detail", kwargs={"pk": blocking.pk}, request=request)
                return Response(
                    {
                        "detail": f"A {blocking.status} collection for {collector} is already in flight",
                        "task_id": blocking.pk,
                        "task_url": task_url,
                        "task_status": blocking.status,
                        "task_data": blocking.task_data,
                    },
                    status=status.HTTP_409_CONFLICT,
                )

            task = Task.objects.create(
                name=f"ondemand_analytics_{collector}_{uuid4().hex}",
                description=f"On-demand analytics collection for {collector}",
                function_name=COLLECT_FUNCTION,
                task_data=task_data,
                is_system_task=False,
                status="pending",
                scheduled_time=None,
                created_by=request.user if request.user.is_authenticated else None,
            )
            return self._response(request, task, "created")
