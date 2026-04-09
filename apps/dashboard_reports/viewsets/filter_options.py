import logging
from collections.abc import Callable
from typing import Any

from ansible_base.rest_pagination import DefaultPaginator
from django.db import DatabaseError
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.viewsets import ReadOnlyModelViewSet

from apps.dashboard_reports.models import JobData
from apps.dashboard_reports.serializers import (
    FilterOptionWithIdSerializer,
)
from apps.tasks.api_utils import build_error_response
from apps.tasks.utils import get_db_connection

logger = logging.getLogger(__name__)


class FilterOptionsViewSet(ReadOnlyModelViewSet):
    """
    Base ViewSet for AWX filter dropdowns (labels, organizations, projects, job templates).
    Handles pagination, search, error handling, and response formatting.
    """

    awx_query_function: Callable[..., list[dict[str, Any]]] | None = None  # To be defined in subclasses
    versioning_class = None  # Disable versioning for this viewset
    pagination_class = DefaultPaginator

    list_error_msg = "Failed to fetch records"
    retrieve_error_msg = "Failed to fetch record"

    def not_found_msg(self, pk: int) -> str:
        """Returns a formatted not found message for a missing record."""
        return f"Record with id {pk} not found"

    def get_queryset(self) -> None:
        """Override to disable queryset (not used for filter dropdowns)."""
        return JobData.objects.none()

    @staticmethod
    def search(request: Request) -> str | None:
        """Extracts search query from request parameters."""
        return request.query_params.get("search", "").strip() or None

    @staticmethod
    def retrieve_response(data: list[dict[str, Any]], error_msg: str) -> Response:
        """
        Returns a single filter dropdown item or error if not found.
        """
        if not data:
            error_response = build_error_response(error_msg, status_code=404)
            return Response(error_response, status=status.HTTP_404_NOT_FOUND)
        serializer = FilterOptionWithIdSerializer(data[0])
        return Response(serializer.data, status=status.HTTP_200_OK)

    def list(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """
        Returns paginated filter dropdown data from AWX database.
        Ensures DB connection is closed after use.
        """
        db_connection = None
        try:
            db_connection = get_db_connection("awx")
            data = self.awx_query_function(db_connection=db_connection, search_str=FilterOptionsViewSet.search(request))
            page = self.paginate_queryset(data)
            return self.get_paginated_response(page)
        except DatabaseError:
            logger.exception(self.list_error_msg)
            error_response = build_error_response(self.list_error_msg, status_code=500)
            return Response(error_response, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        finally:
            if db_connection:
                try:
                    db_connection.close()
                except Exception:
                    logger.warning("Failed to close AWX DB connection in list()")

    def retrieve(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """
        Returns a single filter dropdown item by ID from AWX database.
        Ensures DB connection is closed after use.
        """
        try:
            pk = int(kwargs.get("pk"))
        except (TypeError, ValueError):
            pk = None
        if pk is None or pk <= 0:
            error_response = build_error_response("Invalid ID", status_code=400)
            return Response(error_response, status=status.HTTP_400_BAD_REQUEST)

        db_connection = None
        try:
            db_connection = get_db_connection("awx")
            data = self.awx_query_function(db_connection=db_connection, pk=pk)
            return self.retrieve_response(data, error_msg=self.not_found_msg(pk))
        except DatabaseError:
            logger.exception(self.retrieve_error_msg)
            error_response = build_error_response(self.retrieve_error_msg, status_code=500)
            return Response(error_response, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        finally:
            if db_connection:
                try:
                    db_connection.close()
                except Exception:
                    logger.warning("Failed to close AWX DB connection in retrieve()")
