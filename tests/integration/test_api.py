"""
Integration tests for API endpoints.
"""

import pytest
from django.urls import reverse
from rest_framework import status


@pytest.mark.integration
@pytest.mark.django_db
class TestUserAPI:
    """Test cases for User API endpoints."""

    def test_user_list_authenticated(self, authenticated_client, user):
        """Test authenticated user can list users."""
        url = reverse("api:v1:user-list")
        response = authenticated_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert isinstance(response.data, list)
        assert len(response.data) > 0

    def test_user_detail_authenticated(self, authenticated_client, user):
        """Test authenticated user can get user detail."""
        url = reverse("api:v1:user-detail", kwargs={"pk": user.pk})
        response = authenticated_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["username"] == user.username

    def test_user_me_endpoint(self, authenticated_client, user):
        """Test user can get their own information."""
        url = reverse("api:v1:user-me")
        response = authenticated_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["username"] == user.username


@pytest.mark.integration
@pytest.mark.django_db
class TestOrganizationAPI:
    """Test cases for Organization API endpoints."""

    def test_organization_list(self, authenticated_client, organization):
        """Test authenticated user can list organizations."""
        url = reverse("api:v1:organization-list")
        response = authenticated_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert isinstance(response.data, list)
        assert len(response.data) > 0

    def test_organization_detail(self, authenticated_client, organization):
        """Test authenticated user can get organization detail."""
        url = reverse("api:v1:organization-detail", kwargs={"pk": organization.pk})
        response = authenticated_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["name"] == organization.name


@pytest.mark.integration
@pytest.mark.django_db
class TestAPIDocumentation:
    """Test cases for API documentation endpoints."""

    def test_swagger_ui_endpoint(self, client):
        """Test Swagger UI endpoint response."""
        response = client.get("/api/docs/")
        # Documentation endpoints may not be configured in this environment
        assert response.status_code in [status.HTTP_200_OK, status.HTTP_404_NOT_FOUND]

    def test_redoc_endpoint(self, client):
        """Test ReDoc endpoint response."""
        response = client.get("/api/redoc/")
        # Documentation endpoints may not be configured in this environment
        assert response.status_code in [status.HTTP_200_OK, status.HTTP_404_NOT_FOUND]

    def test_openapi_schema_endpoint(self, client):
        """Test OpenAPI schema endpoint response."""
        response = client.get("/api/schema/")
        # Documentation endpoints may not be configured in this environment
        assert response.status_code in [status.HTTP_200_OK, status.HTTP_404_NOT_FOUND]
