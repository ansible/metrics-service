"""ViewSet for listing AWX job templates as filter dropdown options."""

from drf_spectacular.utils import OpenApiParameter, OpenApiTypes, extend_schema, extend_schema_view

from apps.dashboard_reports.models import AWXJobTemplate
from apps.dashboard_reports.viewsets.filter_options import FilterOptionsViewSet


@extend_schema_view(
    list=extend_schema(
        summary="Get a list of job templates from the local AWX cache.",
        description="Returns a list of job templates cached from the AWX database.",
        parameters=[
            OpenApiParameter(name="page", type=OpenApiTypes.INT, default=1, description="Page number (default: 1)."),
            OpenApiParameter(
                name="page_size", type=OpenApiTypes.INT, default=10, description="Results per page (default: 10)."
            ),
            OpenApiParameter(name="search", type=OpenApiTypes.STR, description="Search by job template name."),
        ],
    ),
    retrieve=extend_schema(
        summary="Get a specific job template from the local AWX cache by ID.",
        description="Returns a single job template record by AWX template ID.",
    ),
)
class JobTemplatesViewSet(FilterOptionsViewSet):
    """
    ViewSet for retrieving AWX job templates from the local cache.

    Data is populated hourly by the sync_dashboard_filter_caches task.

    Endpoints:
        GET /api/v1/dashboard_reports/templates/ - List all job templates (paginated)
        GET /api/v1/dashboard_reports/templates/{id}/ - Get specific job template

    Query Parameters:
        page (int): Page number (default: 1)
        page_size (int): Results per page (default: 10)
        search (str): Search by job template name
    """

    cache_model = AWXJobTemplate
    pk_field = "template_id"
    list_error_msg = "Failed to fetch job templates"
    retrieve_error_msg = "Failed to fetch job template"

    def not_found_msg(self, pk: int) -> str:
        """Return a formatted not-found error message for a missing job template."""
        return f"Job template with id {pk} not found"
