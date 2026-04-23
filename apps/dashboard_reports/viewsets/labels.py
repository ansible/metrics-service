"""ViewSet for listing AWX labels as filter dropdown options."""

from drf_spectacular.utils import OpenApiParameter, OpenApiTypes, extend_schema, extend_schema_view

from apps.dashboard_reports.awx_queries import fetch_labels
from apps.dashboard_reports.viewsets.filter_options import FilterOptionsViewSet


@extend_schema_view(
    list=extend_schema(
        summary="Get a list of labels from AWX database.",
        description="Returns a list of labels from AWX database.",
        parameters=[
            OpenApiParameter(name="page", type=OpenApiTypes.INT, default=1, description="Page number (default: 1)."),
            OpenApiParameter(
                name="page_size", type=OpenApiTypes.INT, default=10, description="Results per page (default: 10)."
            ),
            OpenApiParameter(name="search", type=OpenApiTypes.STR, description="Search by label name."),
        ],
    ),
    retrieve=extend_schema(
        summary="Get a specific label from AWX database by ID.",
        description="Returns a single label record from AWX database by ID.",
    ),
)
class LabelsViewSet(FilterOptionsViewSet):
    """
    ViewSet for retrieving labels from AWX database.

    Provides real-time label data for filter dropdowns with pagination support.

    Endpoints:
        GET /api/v1/dashboard_reports/labels/ - List all labels (paginated)
        GET /api/v1/dashboard_reports/labels/{id}/ - Get specific label

    Query Parameters:
        page (int): Page number (default: 1)
        page_size (int): Results per page (default: 10)
        search (str): Search by label name
    """

    awx_query_function = staticmethod(fetch_labels)
    list_error_msg = "Failed to fetch labels"
    retrieve_error_msg = "Failed to fetch label"

    def not_found_msg(self, pk: int) -> str:
        """Return a formatted not-found error message for a missing label."""
        return f"Label with id {pk} not found"
