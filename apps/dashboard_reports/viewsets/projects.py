"""ViewSet for listing AWX projects as filter dropdown options."""

from drf_spectacular.utils import OpenApiParameter, OpenApiTypes, extend_schema, extend_schema_view

from apps.dashboard_reports.models import AWXProject
from apps.dashboard_reports.viewsets.filter_options import FilterOptionsViewSet


@extend_schema_view(
    list=extend_schema(
        summary="Get a list of projects from the local AWX cache.",
        description="Returns a list of projects cached from the AWX database.",
        parameters=[
            OpenApiParameter(name="page", type=OpenApiTypes.INT, default=1, description="Page number (default: 1)."),
            OpenApiParameter(
                name="page_size", type=OpenApiTypes.INT, default=10, description="Results per page (default: 10)."
            ),
            OpenApiParameter(name="search", type=OpenApiTypes.STR, description="Search by project name."),
        ],
    ),
    retrieve=extend_schema(
        summary="Get a specific project from the local AWX cache by ID.",
        description="Returns a single project record by AWX project ID.",
    ),
)
class ProjectsViewSet(FilterOptionsViewSet):
    """
    ViewSet for retrieving AWX projects from the local cache.

    Data is populated hourly by the sync_dashboard_filter_caches task.

    Endpoints:
        GET /api/v1/dashboard_reports/projects/ - List all projects (paginated)
        GET /api/v1/dashboard_reports/projects/{id}/ - Get specific project

    Query Parameters:
        page (int): Page number (default: 1)
        page_size (int): Results per page (default: 10)
        search (str): Search by project name
    """

    cache_model = AWXProject
    pk_field = "project_id"
    list_error_msg = "Failed to fetch projects"
    retrieve_error_msg = "Failed to fetch project"

    def not_found_msg(self, pk: int) -> str:
        """Return a formatted not-found error message for a missing project."""
        return f"Project with id {pk} not found"
