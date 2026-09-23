"""Analytics API views (ANSTRAT-1587 / AAP-87799)."""

from __future__ import annotations

from datetime import UTC, timedelta
from uuid import uuid4

from ansible_base.rbac.api.permissions import IsSystemAdminOrAuditor
from ansible_base.rest_pagination import DefaultPaginator
from django.db.models import Q
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.reverse import reverse
from rest_framework.views import APIView

from apps.analytics.models import AnalyticsPayload
from apps.analytics.registry import enabled_collectors, get_entry
from apps.analytics.v1.serializers import AnalyticsPayloadSerializer, CollectorDiscoverySerializer


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


class AnalyticsRootView(APIView):
    """List the collectors the analytics API exposes (discovery entry point)."""

    permission_classes = [IsSystemAdminOrAuditor]

    def get(self, request, *args, **kwargs):
        """Return the enabled collectors and their rows URLs."""
        serializer = CollectorDiscoverySerializer(
            enabled_collectors().values(),
            many=True,
            context={"request": request},
        )
        return Response({"collectors": serializer.data})


class CollectorRowsView(generics.ListAPIView):
    """Return one collector's stored raw payloads, window-overlap filtered + paginated."""

    permission_classes = [IsSystemAdminOrAuditor]
    serializer_class = AnalyticsPayloadSerializer
    pagination_class = DefaultPaginator
    # Disable the DAB field-lookup/filter backends: they would treat ``since``/``until`` as
    # exact-match field lookups on the model and override our window-*overlap* semantics. We keep
    # DAB pagination but own the filtering here.
    filter_backends: list = []

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
        return super().list(request, *args, **kwargs)


class CollectorCollectView(APIView):
    """Create one claimless on-demand collection task for an enabled collector."""

    permission_classes = [IsSystemAdminOrAuditor]

    def _resolve_window(self, entry, request):
        """Parse request bounds, apply mode defaults, and return a task window or an error."""
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

        if not entry.accepts_since_until:
            if since is not None or until is not None:
                return None, Response(
                    {"detail": f"Collector {entry.name} is snapshot-only and does not accept since/until"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            return (None, None), None

        default_since, default_until = _default_window(entry.mode, timezone.now())
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

    def post(self, request, *args, **kwargs):
        """Create a pending task and return its details without claiming a payload row."""
        collector = self.kwargs["collector"]
        entry = get_entry(collector)
        if entry is None or not entry.enabled:
            return Response(
                {"detail": f"Unknown or disabled collector: {collector}"},
                status=status.HTTP_404_NOT_FOUND,
            )

        if "source" in request.data:
            return Response(
                {"detail": "source is not configurable for collection tasks"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        window, error = self._resolve_window(entry, request)
        if error is not None:
            return error
        since, until = window

        task_data = {"collector": collector}
        if since is not None:
            task_data["since"] = since.isoformat()
        if until is not None:
            task_data["until"] = until.isoformat()

        from apps.tasks.models import Task

        task = Task.objects.create(
            name=f"ondemand_analytics_{collector}_{uuid4().hex}",
            description=f"On-demand analytics collection for {collector}",
            function_name="collect_analytics_on_demand",
            task_data=task_data,
            is_system_task=False,
            status="pending",
            scheduled_time=None,
            created_by=request.user if request.user.is_authenticated else None,
        )
        task_url = reverse("tasks:v1:task-detail", kwargs={"pk": task.pk}, request=request)
        response = Response(
            {
                "task_id": task.pk,
                "task_url": task_url,
                "collector": collector,
                "task_data": task_data,
            },
            status=status.HTTP_202_ACCEPTED,
        )
        response["Location"] = task_url
        return response
