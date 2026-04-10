"""
Test dashboard_reports API endpoints and URL routing.
"""

import pytest
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import resolve
from rest_framework.test import APIClient

from tests.test_utils import get_test_password

User = get_user_model()

empty_list_response = {
    "count": 0,
    "next": None,
    "previous": None,
    "results": [],
}


@pytest.mark.integration
class TestDashboardReportsURLs(TestCase):
    """Test dashboard_reports API endpoints and URL routing."""

    def setUp(self):
        """Set up test environment."""
        super().setUp()
        self.api_client = APIClient()
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password=get_test_password()
        )

    def test_dashboard_reports_endpoint_resolution(self):
        """Test that all dashboard_reports endpoints resolve correctly."""
        endpoints = [
            "/api/v1/dashboard_reports/organizations/",
            "/api/v1/dashboard_reports/templates/",
            "/api/v1/dashboard_reports/projects/",
            "/api/v1/dashboard_reports/labels/",
            "/api/v1/dashboard_reports/report/",
        ]

        for endpoint in endpoints:
            resolver_match = resolve(endpoint)
            assert resolver_match is not None, f"Failed to resolve {endpoint}"

    def test_dashboard_reports_organizations_endpoint(self):
        """Test organizations endpoint."""
        response = self.api_client.get("/api/v1/dashboard_reports/organizations/")
        # Should respond (200, 403, 404, or 405 depending on permissions and config)
        assert response.status_code in [200]

    def test_dashboard_reports_templates_endpoint(self):
        """Test job templates endpoint."""
        response = self.api_client.get("/api/v1/dashboard_reports/templates/")
        assert response.status_code in [200]
        assert response.json() == empty_list_response

    def test_dashboard_reports_projects_endpoint(self):
        """Test projects endpoint."""
        response = self.api_client.get("/api/v1/dashboard_reports/projects/")
        assert response.status_code in [200]
        assert response.json() == empty_list_response

    def test_dashboard_reports_labels_endpoint(self):
        """Test labels endpoint."""
        response = self.api_client.get("/api/v1/dashboard_reports/labels/")
        assert response.status_code in [200]
        assert response.json() == empty_list_response

    def test_dashboard_reports_report_endpoint(self):
        """Test report endpoint."""
        response = self.api_client.get("/api/v1/dashboard_reports/report/?period=last_7_days")
        assert response.status_code in [200]
        assert response.json() == empty_list_response

    def test_dashboard_reports_authenticated_access(self):
        """Test dashboard_reports endpoints with authenticated user."""
        self.api_client.force_authenticate(user=self.user)

        endpoints = [
            "/api/v1/dashboard_reports/organizations/",
            "/api/v1/dashboard_reports/templates/",
            "/api/v1/dashboard_reports/projects/",
            "/api/v1/dashboard_reports/labels/",
            "/api/v1/dashboard_reports/report/?period=last_7_days",
        ]

        for endpoint in endpoints:
            response = self.api_client.get(endpoint)
            assert response.status_code == 200, f"Expected 200 for authenticated access to {endpoint}, got {response.status_code}"

    def test_dashboard_reports_post_endpoints(self):
        """Test POST requests to dashboard_reports endpoints."""
        self.api_client.force_authenticate(user=self.user)

        endpoints = [
            "/api/v1/dashboard_reports/organizations/",
            "/api/v1/dashboard_reports/templates/",
            "/api/v1/dashboard_reports/projects/",
            "/api/v1/dashboard_reports/labels/",
            "/api/v1/dashboard_reports/report/?period=last_7_days",
        ]

        for endpoint in endpoints:
            response = self.api_client.post(endpoint, {})
            # POST is not allowed (405)
            assert response.status_code in [405]

    def test_dashboard_reports_filtering(self):
        """Test that dashboard_reports endpoints support filtering."""
        self.api_client.force_authenticate(user=self.user)

        # Test with filter parameters
        response = self.api_client.get("/api/v1/dashboard_reports/organizations/?limit=10")
        assert response.status_code in [200]
        assert response.json() == empty_list_response

        response = self.api_client.get("/api/v1/dashboard_reports/templates/?offset=0")
        assert response.status_code in [200]
        assert response.json() == empty_list_response

    def test_dashboard_reports_pagination(self):
        """Test pagination on dashboard_reports endpoints."""
        self.api_client.force_authenticate(user=self.user)

        endpoints = [
            "/api/v1/dashboard_reports/organizations/?page=1",
            "/api/v1/dashboard_reports/templates/?page=1",
            "/api/v1/dashboard_reports/projects/?page=1",
            "/api/v1/dashboard_reports/labels/?page=1",
            "/api/v1/dashboard_reports/report/?period=last_7_days&page=1",
        ]

        for endpoint in endpoints:
            response = self.api_client.get(endpoint)
            # Pagination may or may not be supported
            assert response.status_code in [200]
            assert response.json() == empty_list_response

    def test_dashboard_reports_detail_endpoints(self):
        """Test detail endpoints with IDs."""
        self.api_client.force_authenticate(user=self.user)

        # Test with various ID values
        test_ids = [1, 999999, "invalid"]

        endpoints_template = [
            "/api/v1/dashboard_reports/organizations/{id}/",
            "/api/v1/dashboard_reports/templates/{id}/",
            "/api/v1/dashboard_reports/projects/{id}/",
            "/api/v1/dashboard_reports/labels/{id}/",
        ]

        for test_id in test_ids:
            for endpoint_template in endpoints_template:
                endpoint = endpoint_template.format(id=test_id)
                response = self.api_client.get(endpoint)
                # Should not get 500 errors
                assert response.status_code != 500, f"Server error for {endpoint}"
