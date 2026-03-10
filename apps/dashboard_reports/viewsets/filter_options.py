import logging
from collections.abc import Callable
from typing import Any

from django.db import DatabaseError
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.viewsets import ReadOnlyModelViewSet

from apps.core.permissions import DeveloperModeRequired
from apps.dashboard_reports.serializers import (
    FilterOptionWithIdSerializer,
    PaginatedFilterOptionsSerializer,
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
    permission_classes = [DeveloperModeRequired]

    list_error_msg = "Failed to fetch records"
    retrieve_error_msg = "Failed to fetch record"

    def not_found_msg(self, pk: int) -> str:
        """Returns a formatted not found message for a missing record."""
        return f"Record with id {pk} not found"

    def get_queryset(self) -> None:
        """Override to disable queryset (not used for filter dropdowns)."""
        return None

    @staticmethod
    def search(request: Request) -> str | None:
        """Extracts search query from request parameters."""
        return request.query_params.get("search", "").strip() or None

    @staticmethod
    def _build_pagination_url(base_url: str, page: int, page_size: int, search_query: str | None) -> str:
        """Builds a pagination URL with page, page_size, and optional search query."""
        url = f"{base_url}?page={page}&page_size={page_size}"
        if search_query:
            url += f"&search={search_query}"
        return url

    @staticmethod
    def paginate(request: Request, data: list[dict[str, Any]]) -> Response:
        """
        Paginates the filter dropdown data and builds pagination URLs.
        """
        # Parse pagination parameters
        try:
            page = int(request.query_params.get("page", 1))
            page_size = int(request.query_params.get("page_size", 10))
        except (ValueError, TypeError):
            page = 1
            page_size = 10

        page = max(page, 1)
        if page_size < 1:
            page_size = 10

        search_query = FilterOptionsViewSet.search(request)
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        paginated_data = data[start_idx:end_idx]

        # Build pagination URLs
        base_url = request.build_absolute_uri(request.path)
        next_url = (
            FilterOptionsViewSet._build_pagination_url(base_url, page + 1, page_size, search_query)
            if end_idx < len(data)
            else None
        )
        previous_url = (
            FilterOptionsViewSet._build_pagination_url(base_url, page - 1, page_size, search_query)
            if page > 1
            else None
        )

        # Build response
        response_data = {"count": len(data), "next": next_url, "previous": previous_url, "results": paginated_data}

        serializer = PaginatedFilterOptionsSerializer(response_data)

        return Response(serializer.data, status=status.HTTP_200_OK)

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
            return FilterOptionsViewSet.paginate(request, data)
        except DatabaseError as e:
            logger.error(f"{self.list_error_msg}: {str(e)}")
            error_response = build_error_response(f"{self.list_error_msg}: {str(e)}", status_code=500)
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
        pk = kwargs.get("pk")
        pk = int(pk) if pk and str(pk).isdigit() else None
        if pk is None:
            error_response = build_error_response("Invalid ID", status_code=400)
            return Response(error_response, status=status.HTTP_400_BAD_REQUEST)
        db_connection = get_db_connection("awx")
        try:
            data = self.awx_query_function(db_connection=db_connection, pk=pk)
            return self.retrieve_response(data, error_msg=self.not_found_msg(pk))
        except DatabaseError as e:
            logger.error(f"{self.retrieve_error_msg}: {str(e)}")
            error_response = build_error_response(f"{self.retrieve_error_msg}: {str(e)}", status_code=500)
            return Response(error_response, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        finally:
            try:
                db_connection.close()
            except Exception:
                logger.warning("Failed to close AWX DB connection in retrieve()")
