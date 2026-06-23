"""ViewSet for listing AWX organizations as filter dropdown options."""

from drf_spectacular.utils import OpenApiParameter, OpenApiTypes, extend_schema, extend_schema_view

from apps.dashboard_reports.models import AWXOrganization
from apps.dashboard_reports.viewsets.filter_options import FilterOptionsViewSet


@extend_schema_view(
    list=extend_schema(
        summary="Get a list of organizations from the local AWX cache.",
        description="Returns a list of organizations cached from the AWX database.",
        parameters=[
            OpenApiParameter(name="page", type=OpenApiTypes.INT, default=1, description="Page number (default: 1)."),
            OpenApiParameter(
                name="page_size", type=OpenApiTypes.INT, default=10, description="Results per page (default: 10)."
            ),
            OpenApiParameter(name="search", type=OpenApiTypes.STR, description="Search by organization name."),
        ],
    ),
    retrieve=extend_schema(
        summary="Get a specific organization from the local AWX cache by ID.",
        description="Returns a single organization record by AWX organization ID.",
    ),
)
class OrganizationsViewSet(FilterOptionsViewSet):
    """
    ViewSet for retrieving AWX organizations from the local cache.

    Data is populated hourly by the sync_dashboard_filter_caches task.

    Endpoints:
        GET /api/v1/dashboard_reports/organizations/ - List all organizations (paginated)
        GET /api/v1/dashboard_reports/organizations/{id}/ - Get specific organization

    Query Parameters:
        page (int): Page number (default: 1)
        page_size (int): Results per page (default: 10)
        search (str): Search by organization name
    """

    cache_model = AWXOrganization
    pk_field = "org_id"
    list_error_msg = "Failed to fetch organizations"
    retrieve_error_msg = "Failed to fetch organization"

    def not_found_msg(self, pk: int) -> str:
        """Return a formatted not-found error message for a missing organization."""
        return f"Organization with id {pk} not found"
