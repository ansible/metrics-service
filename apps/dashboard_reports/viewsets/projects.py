"""ViewSet for listing AWX projects as filter dropdown options."""

from drf_spectacular.utils import OpenApiParameter, OpenApiTypes, extend_schema, extend_schema_view

from apps.dashboard_reports.awx_queries import fetch_projects
from apps.dashboard_reports.viewsets.filter_options import FilterOptionsViewSet


@extend_schema_view(
    list=extend_schema(
        summary="Get a list of projects from AWX database.",
        description="Returns a list of projects from AWX database.",
        parameters=[
            OpenApiParameter(name="page", type=OpenApiTypes.INT, default=1, description="Page number (default: 1)."),
            OpenApiParameter(
                name="page_size", type=OpenApiTypes.INT, default=10, description="Results per page (default: 10)."
            ),
            OpenApiParameter(name="search", type=OpenApiTypes.STR, description="Search by project name."),
        ],
    ),
    retrieve=extend_schema(
        summary="Get a specific project from AWX database by ID.",
        description="Returns a single project record from AWX database by ID.",
    ),
)
class ProjectsViewSet(FilterOptionsViewSet):
    """
    ViewSet for retrieving projects from AWX database.

    Provides real-time project data for filter dropdowns with pagination support.

    Endpoints:
        GET /api/v1/dashboard_reports/projects/ - List all projects (paginated)
        GET /api/v1/dashboard_reports/projects/{id}/ - Get specific project

    Query Parameters:
        page (int): Page number (default: 1)
        page_size (int): Results per page (default: 10)
        search (str): Search by project name
    """

    awx_query_function = staticmethod(fetch_projects)
    list_error_msg = "Failed to fetch projects"
    retrieve_error_msg = "Failed to fetch project"

    def not_found_msg(self, pk: int) -> str:
        """Return a formatted not-found error message for a missing project."""
        return f"Project with id {pk} not found"
