"""ViewSet for listing AWX organizations as filter dropdown options."""

from apps.dashboard_reports.awx_queries import fetch_organizations
from apps.dashboard_reports.viewsets import FilterOptionsViewSet


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

    awx_query_function = fetch_organizations
    list_error_msg = "Failed to fetch organizations"
    retrieve_error_msg = "Failed to fetch organization"

    def not_found_msg(self, pk: int) -> str:
        """Return a formatted not-found error message for a missing organization."""
        return f"Organization with id {pk} not found"
