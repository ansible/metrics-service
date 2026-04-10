"""ViewSet for listing AWX labels as filter dropdown options."""

from apps.dashboard_reports.awx_queries import fetch_labels
from apps.dashboard_reports.viewsets import FilterOptionsViewSet


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

    awx_query_function = fetch_labels
    list_error_msg = "Failed to fetch labels"
    retrieve_error_msg = "Failed to fetch label"

    def not_found_msg(self, pk: int) -> str:
        """Return a formatted not-found error message for a missing label."""
        return f"Label with id {pk} not found"
