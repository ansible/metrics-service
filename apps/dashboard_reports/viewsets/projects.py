"""ViewSet for listing AWX projects as filter dropdown options."""

from apps.dashboard_reports.awx_queries import fetch_projects
from apps.dashboard_reports.viewsets.filter_options import FilterOptionsViewSet


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
