from apps.dashboard_reports.awx_queries import fetch_templates
from apps.dashboard_reports.viewsets import FilterOptionsViewSet


class JobTemplatesViewSet(FilterOptionsViewSet):
    """
    ViewSet for retrieving job templates from AWX database.

    Provides real-time job template data for filter dropdowns with pagination support.

    Endpoints:
        GET /api/v1/dashboard_reports/job_templates/ - List all job templates (paginated)
        GET /api/v1/dashboard_reports/job_templates/{id}/ - Get specific job template

    Query Parameters:
        page (int): Page number (default: 1)
        page_size (int): Results per page (default: 10)
        search (str): Search by job template name
    """

    awx_query_function = fetch_templates
    list_error_msg = "Failed to fetch job templates"
    retrieve_error_msg = "Failed to fetch job template"

    def not_found_msg(self, pk: int) -> str:
        return f"Job template with id {pk} not found"
