"""ViewSet for listing AWX labels as filter dropdown options."""

from drf_spectacular.utils import OpenApiParameter, OpenApiTypes, extend_schema, extend_schema_view

from apps.dashboard_reports.models import AWXLabel
from apps.dashboard_reports.viewsets.filter_options import FilterOptionsViewSet


@extend_schema_view(
    list=extend_schema(
        summary="Get a list of labels from the local AWX cache.",
        description="Returns a list of labels cached from the AWX database.",
        parameters=[
            OpenApiParameter(name="page", type=OpenApiTypes.INT, default=1, description="Page number (default: 1)."),
            OpenApiParameter(
                name="page_size", type=OpenApiTypes.INT, default=10, description="Results per page (default: 10)."
            ),
            OpenApiParameter(name="search", type=OpenApiTypes.STR, description="Search by label name."),
        ],
    ),
    retrieve=extend_schema(
        summary="Get a specific label from the local AWX cache by ID.",
        description="Returns a single label record by AWX label ID.",
    ),
)
class LabelsViewSet(FilterOptionsViewSet):
    """
    ViewSet for retrieving AWX labels from the local cache.

    Data is populated hourly by the sync_dashboard_filter_caches task.

    Endpoints:
        GET /api/v1/dashboard_reports/labels/ - List all labels (paginated)
        GET /api/v1/dashboard_reports/labels/{id}/ - Get specific label

    Query Parameters:
        page (int): Page number (default: 1)
        page_size (int): Results per page (default: 10)
        search (str): Search by label name
    """

    cache_model = AWXLabel
    pk_field = "label_id"
    list_error_msg = "Failed to fetch labels"
    retrieve_error_msg = "Failed to fetch label"

    def not_found_msg(self, pk: int) -> str:
        """Return a formatted not-found error message for a missing label."""
        return f"Label with id {pk} not found"
