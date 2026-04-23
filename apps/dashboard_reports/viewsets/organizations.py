"""ViewSet for listing AWX organizations as filter dropdown options."""

from drf_spectacular.utils import OpenApiParameter, OpenApiTypes, extend_schema, extend_schema_view

from apps.dashboard_reports.awx_queries import fetch_organizations
from apps.dashboard_reports.viewsets.filter_options import FilterOptionsViewSet


@extend_schema_view(
    list=extend_schema(
        summary="Get a list of organizations from AWX database.",
        description="Returns a list of organizations from AWX database.",
        parameters=[
            OpenApiParameter(name="page", type=OpenApiTypes.INT, default=1, description="Page number (default: 1)."),
            OpenApiParameter(
                name="page_size", type=OpenApiTypes.INT, default=10, description="Results per page (default: 10)."
            ),
            OpenApiParameter(name="search", type=OpenApiTypes.STR, description="Search by organization name."),
        ],
    ),
    retrieve=extend_schema(
        summary="Get a specific organization from AWX database by ID.",
        description="Returns a single organization record from AWX database by ID.",
    ),
)
class OrganizationsViewSet(FilterOptionsViewSet):
    """
    ViewSet for retrieving organizations from AWX database.

    Provides real-time organization data for filter dropdowns with pagination support.

    Endpoints:
        GET /api/v1/dashboard_reports/organizations/ - List all organizations (paginated)
        GET /api/v1/dashboard_reports/organizations/{id}/ - Get specific organization

    Query Parameters:
        page (int): Page number (default: 1)
        page_size (int): Results per page (default: 10)
        search (str): Search by organization name
    """

    awx_query_function = staticmethod(fetch_organizations)
    list_error_msg = "Failed to fetch organizations"
    retrieve_error_msg = "Failed to fetch organization"

    def not_found_msg(self, pk: int) -> str:
        """Return a formatted not-found error message for a missing organization."""
        return f"Organization with id {pk} not found"
