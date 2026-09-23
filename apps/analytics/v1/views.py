"""Read-only analytics API views (ANSTRAT-1587 / AAP-87799)."""

from __future__ import annotations

from datetime import UTC

from ansible_base.rbac.api.permissions import IsSystemAdminOrAuditor
from ansible_base.rest_pagination import DefaultPaginator
from django.db.models import Q
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.response import Response
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
