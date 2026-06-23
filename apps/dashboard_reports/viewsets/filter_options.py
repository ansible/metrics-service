"""Base ViewSet for filter dropdown endpoints served from local AWX cache tables."""

import logging
from typing import Any

from ansible_base.rbac.api.permissions import IsSystemAdminOrAuditor
from ansible_base.rest_pagination import DefaultPaginator
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from apps.dashboard_reports.serializers import FilterOptionWithIdSerializer
from apps.tasks.api_utils import build_error_response

logger = logging.getLogger(__name__)


class FilterOptionsViewSet(GenericViewSet):
    """
    Base ViewSet for AWX filter dropdowns (labels, organizations, projects, job templates).

    Reads from local cache tables populated by the sync_dashboard_filter_caches hourly task
    so that no live Controller DB connection is required at request time.

    Subclasses set:
        cache_model  — the Django model holding cached (id, name) pairs
        pk_field     — the model field name for the AWX entity ID (e.g. "org_id")
    """

    cache_model = None
    pk_field = None

    versioning_class = None
    pagination_class = DefaultPaginator
    permission_classes = [IsSystemAdminOrAuditor]
    serializer_class = FilterOptionWithIdSerializer

    list_error_msg = "Failed to fetch records"
    retrieve_error_msg = "Failed to fetch record"

    def not_found_msg(self, pk: int) -> str:
        return f"Record with id {pk} not found"

    def get_queryset(self):
        """Return an empty queryset — required by DRF for schema generation."""
        return self.cache_model.objects.none()

    def _qs(self):
        """Return a queryset of (pk_field, name) value dicts for this cache model."""
        return self.cache_model.objects.values(self.pk_field, "name")

    def _to_item(self, row: dict) -> dict:
        """Remap the pk_field key to 'id' so responses match FilterOptionWithIdSerializer."""
        return {"id": row[self.pk_field], "name": row["name"]}

    def list(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Return paginated, optionally searched filter options from the local cache."""
        qs = self._qs()
        search = (request.query_params.get("search") or "").strip()
        if search:
            qs = qs.filter(name__icontains=search)
        qs = qs.order_by("name")
        page = self.paginate_queryset(qs)
        items = [self._to_item(row) for row in (page if page is not None else qs)]
        if page is not None:
            return self.get_paginated_response(items)
        return Response(items)

    def retrieve(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Return a single filter option by its AWX entity ID."""
        try:
            pk = int(kwargs.get("pk"))
        except (TypeError, ValueError):
            return Response(build_error_response("Invalid ID", status_code=400), status=status.HTTP_400_BAD_REQUEST)
        if pk <= 0:
            return Response(
                build_error_response(self.not_found_msg(pk), status_code=404), status=status.HTTP_404_NOT_FOUND
            )
        try:
            row = self._qs().get(**{self.pk_field: pk})
        except self.cache_model.DoesNotExist:
            return Response(
                build_error_response(self.not_found_msg(pk), status_code=404), status=status.HTTP_404_NOT_FOUND
            )
        return Response(FilterOptionWithIdSerializer(self._to_item(row)).data, status=status.HTTP_200_OK)
