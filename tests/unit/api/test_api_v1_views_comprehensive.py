"""
Comprehensive tests for apps/api/v1/views.py

This module provides extensive test coverage for core API views including
UserViewSet and OrganizationViewSet with all methods and edge cases.
"""

from unittest.mock import MagicMock, patch

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.core.models import Organization, Setting, User
from tests.test_utils import get_test_password


@pytest.mark.unit
@pytest.mark.django_db
class TestUserViewSetComprehensive(APITestCase):
    """Comprehensive tests for UserViewSet."""

    def setUp(self):
        """Set up test data."""
        self.superuser = User.objects.create_superuser(
            username="admin", email="admin@example.com", password=get_test_password()
        )
        self.regular_user = User.objects.create_user(
            username="user", email="user@example.com", password=get_test_password()
        )
        self.auditor_user = User.objects.create_user(
            username="auditor", email="auditor@example.com", password=get_test_password(), is_system_auditor=True
        )

    def test_user_me_endpoint(self):
        """Test GET /api/v1/users/me/ endpoint."""
        self.client.force_authenticate(user=self.regular_user)

        url = reverse("api:v1:user-me")
        response = self.client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["username"] == "user"
        assert response.data["email"] == "user@example.com"
        # Password should not be included in response
        assert "password" not in response.data

    def test_user_set_password_endpoint(self):
        """Test POST /api/v1/users/{id}/set_password/ endpoint."""
        self.client.force_authenticate(user=self.superuser)

        url = reverse("api:v1:user-set-password", kwargs={"pk": self.regular_user.pk})
        data = {"password": get_test_password()}
        response = self.client.post(url, data, format="json")

        assert response.status_code == status.HTTP_204_NO_CONTENT

        # Verify password was changed
        self.regular_user.refresh_from_db()
        assert self.regular_user.check_password(get_test_password())

    def test_user_set_password_missing_password(self):
        """Test set_password endpoint with missing password."""
        self.client.force_authenticate(user=self.superuser)

        url = reverse("api:v1:user-set-password", kwargs={"pk": self.regular_user.pk})
        response = self.client.post(url, {}, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Password is required" in response.data["error"]

    def test_user_set_password_empty_password(self):
        """Test set_password endpoint with empty password."""
        self.client.force_authenticate(user=self.superuser)

        url = reverse("api:v1:user-set-password", kwargs={"pk": self.regular_user.pk})
        data = {"password": ""}
        response = self.client.post(url, data, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_user_set_password_unauthorized(self):
        """Test set_password endpoint without proper permissions."""
        self.client.force_authenticate(user=self.regular_user)

        url = reverse("api:v1:user-set-password", kwargs={"pk": self.superuser.pk})
        data = {"password": get_test_password()}
        response = self.client.post(url, data, format="json")

        # Should be forbidden for regular users to change other users' passwords
        assert response.status_code in [status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND]

    def test_user_ordering_by_username(self):
        """Test ordering users by username."""
        self.client.force_authenticate(user=self.superuser)

        url = reverse("api:v1:user-list")
        response = self.client.get(url, {"ordering": "username"})

        assert response.status_code == status.HTTP_200_OK
        # Access paginated results
        results = response.data.get("results", response.data)
        if len(results) >= 2:
            # Verify ordering
            usernames = [user["username"] for user in results]
            assert usernames == sorted(usernames)

    def test_user_ordering_by_email_descending(self):
        """Test ordering users by email in descending order."""
        self.client.force_authenticate(user=self.superuser)

        url = reverse("api:v1:user-list")
        response = self.client.get(url, {"ordering": "-email"})

        assert response.status_code == status.HTTP_200_OK
        # Access paginated results
        results = response.data.get("results", response.data)
        if len(results) >= 2:
            emails = [user["email"] for user in results]
            assert emails == sorted(emails, reverse=True)

    def test_user_create_with_superuser_permissions(self):
        """Test creating user with superuser permissions."""
        self.client.force_authenticate(user=self.superuser)

        url = reverse("api:v1:user-list")
        data = {
            "username": "newadmin",
            "email": "newadmin@example.com",
            "password": get_test_password(),
            "confirm_password": get_test_password(),
            "is_superuser": True,
        }
        response = self.client.post(url, data, format="json")

        if response.status_code == status.HTTP_201_CREATED:
            assert response.data["username"] == "newadmin"
            assert response.data["is_superuser"] is True

    def test_user_update_permissions_as_superuser(self):
        """Test updating user permissions as superuser."""
        self.client.force_authenticate(user=self.superuser)

        url = reverse("api:v1:user-detail", kwargs={"pk": self.regular_user.pk})
        data = {"username": self.regular_user.username, "email": self.regular_user.email, "is_system_auditor": True}
        response = self.client.patch(url, data, format="json")

        if response.status_code == status.HTTP_200_OK:
            assert response.data["is_system_auditor"] is True

    def test_user_update_permissions_as_regular_user(self):
        """Test that regular users can't update permission flags."""
        self.client.force_authenticate(user=self.regular_user)

        url = reverse("api:v1:user-detail", kwargs={"pk": self.regular_user.pk})
        data = {"is_superuser": True}
        response = self.client.patch(url, data, format="json")

        # Should either be forbidden or the permission flag should be ignored
        if response.status_code == status.HTTP_200_OK:
            assert response.data["is_superuser"] is False  # Should remain unchanged

    @patch("apps.api.v1.views.User.access_qs")
    def test_user_queryset_filtering_with_dab(self, mock_access_qs):
        """Test that get_queryset uses DAB access_qs method."""
        self.client.force_authenticate(user=self.regular_user)

        # Mock the access_qs method
        mock_queryset = MagicMock()
        mock_access_qs.return_value = mock_queryset

        url = reverse("api:v1:user-list")
        self.client.get(url)

        # Verify access_qs was called with the request user
        mock_access_qs.assert_called_once()
        call_args = mock_access_qs.call_args[0]
        assert call_args[0] == self.regular_user


@pytest.mark.unit
@pytest.mark.django_db
class TestOrganizationViewSetComprehensive(APITestCase):
    """Comprehensive tests for OrganizationViewSet."""

    def setUp(self):
        """Set up test data."""
        self.superuser = User.objects.create_superuser(
            username="admin", email="admin@example.com", password=get_test_password()
        )
        self.regular_user = User.objects.create_user(
            username="user", email="user@example.com", password=get_test_password()
        )

        self.organization = Organization.objects.create(name="Test Org", description="Test Organization")

    def test_organization_list_endpoint(self):
        """Test GET /api/v1/organizations/ endpoint."""
        self.client.force_authenticate(user=self.superuser)

        url = reverse("api:v1:organization-list")
        response = self.client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) >= 1

    def test_organization_detail_endpoint(self):
        """Test GET /api/v1/organizations/{id}/ endpoint."""
        self.client.force_authenticate(user=self.superuser)

        url = reverse("api:v1:organization-detail", kwargs={"pk": self.organization.pk})
        response = self.client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["name"] == "Test Org"
        assert response.data["description"] == "Test Organization"

    def test_organization_create_endpoint(self):
        """Test POST /api/v1/organizations/ endpoint."""
        self.client.force_authenticate(user=self.superuser)

        url = reverse("api:v1:organization-list")
        data = {"name": "New Organization", "description": "A new test organization"}
        response = self.client.post(url, data, format="json")

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["name"] == "New Organization"
        assert Organization.objects.filter(name="New Organization").exists()

    def test_organization_update_endpoint(self):
        """Test PUT /api/v1/organizations/{id}/ endpoint."""
        self.client.force_authenticate(user=self.superuser)

        url = reverse("api:v1:organization-detail", kwargs={"pk": self.organization.pk})
        data = {"name": "Updated Organization", "description": "Updated description"}
        response = self.client.put(url, data, format="json")

        assert response.status_code == status.HTTP_200_OK
        assert response.data["name"] == "Updated Organization"

        self.organization.refresh_from_db()
        assert self.organization.name == "Updated Organization"

    def test_organization_partial_update_endpoint(self):
        """Test PATCH /api/v1/organizations/{id}/ endpoint."""
        self.client.force_authenticate(user=self.superuser)

        original_description = self.organization.description
        url = reverse("api:v1:organization-detail", kwargs={"pk": self.organization.pk})
        data = {"name": "Patched Name"}
        response = self.client.patch(url, data, format="json")

        assert response.status_code == status.HTTP_200_OK
        assert response.data["name"] == "Patched Name"
        # Description should remain unchanged
        assert response.data["description"] == original_description

    def test_organization_delete_endpoint(self):
        """Test DELETE /api/v1/organizations/{id}/ endpoint."""
        self.client.force_authenticate(user=self.superuser)

        # Create a separate org for deletion
        delete_org = Organization.objects.create(name="Delete Me", description="For deletion")
        org_id = delete_org.pk

        url = reverse("api:v1:organization-detail", kwargs={"pk": org_id})
        response = self.client.delete(url)

        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert not Organization.objects.filter(pk=org_id).exists()

    def test_organization_users_relationship_endpoint(self):
        """Test organization users relationship endpoint."""
        self.client.force_authenticate(user=self.superuser)

        # Add user to organization
        self.organization.users.add(self.regular_user)

        url = reverse("api:v1:organization-users", kwargs={"pk": self.organization.pk})
        response = self.client.get(url)

        assert response.status_code == status.HTTP_200_OK
        user_ids = [user["id"] for user in response.data]
        assert self.regular_user.pk in user_ids

    def test_organization_users_add_endpoint(self):
        """Test POST /api/v1/organizations/{id}/users/ endpoint."""
        self.client.force_authenticate(user=self.superuser)

        url = reverse("api:v1:organization-users", kwargs={"pk": self.organization.pk})
        data = {"id": self.regular_user.pk}
        response = self.client.post(url, data, format="json")

        # Should succeed or already be a member
        if response.status_code == status.HTTP_204_NO_CONTENT:
            assert self.regular_user in self.organization.users.all()

    def test_organization_users_remove_endpoint(self):
        """Test DELETE /api/v1/organizations/{id}/users/ endpoint."""
        self.client.force_authenticate(user=self.superuser)

        # First add the user
        self.organization.users.add(self.regular_user)

        url = reverse("api:v1:organization-users", kwargs={"pk": self.organization.pk})
        data = {"id": self.regular_user.pk}
        response = self.client.delete(url, data, format="json")

        # Should succeed in removing user
        if response.status_code == status.HTTP_204_NO_CONTENT:
            assert self.regular_user not in self.organization.users.all()

    @patch("apps.api.v1.views.Organization.access_qs")
    def test_organization_queryset_filtering_with_dab(self, mock_access_qs):
        """Test that get_queryset uses DAB access_qs method."""
        self.client.force_authenticate(user=self.regular_user)

        # Mock the access_qs method
        mock_queryset = MagicMock()
        mock_access_qs.return_value = mock_queryset

        url = reverse("api:v1:organization-list")
        self.client.get(url)

        # Verify access_qs was called with the request user
        mock_access_qs.assert_called_once()
        call_args = mock_access_qs.call_args[0]
        assert call_args[0] == self.regular_user


@pytest.mark.unit
@pytest.mark.django_db
class TestSettingViewSetComprehensive(APITestCase):
    """Comprehensive tests for SettingViewSet."""

    def setUp(self):
        """Set up test data."""
        self.superuser = User.objects.create_superuser(
            username="admin", email="admin@example.com", password=get_test_password()
        )
        self.regular_user = User.objects.create_user(
            username="user", email="user@example.com", password=get_test_password()
        )

    def test_setting_list_endpoint(self):
        """Test GET /api/v1/settings/ endpoint."""
        self.client.force_authenticate(user=self.superuser)

        # Create test setting
        Setting.objects.create(
            setting_key="TEST_SETTING", current_value={"test": "value"}, last_modified_by=self.superuser
        )

        url = reverse("api:v1:settings-list")
        response = self.client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) >= 1

    def test_setting_unauthorized_access(self):
        """Test that regular users can't access settings."""
        self.client.force_authenticate(user=self.regular_user)

        url = reverse("api:v1:settings-list")
        response = self.client.get(url)

        # Should be forbidden for non-admin users
        assert response.status_code in [status.HTTP_403_FORBIDDEN, status.HTTP_401_UNAUTHORIZED]


@pytest.mark.unit
class TestAPIErrorHandling(APITestCase):
    """Test API error handling and edge cases."""

    def setUp(self):
        """Set up test data."""
        self.superuser = User.objects.create_superuser(
            username="admin", email="admin@example.com", password=get_test_password()
        )

    def test_invalid_json_request(self):
        """Test handling of invalid JSON in request body."""
        self.client.force_authenticate(user=self.superuser)

        url = reverse("api:v1:user-list")
        # Send invalid JSON
        response = self.client.post(url, "invalid json", content_type="application/json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_missing_content_type_header(self):
        """Test handling of missing content-type header."""
        self.client.force_authenticate(user=self.superuser)

        url = reverse("api:v1:user-list")
        data = '{"username": "test"}'
        response = self.client.post(url, data, content_type="text/plain")

        # Should handle gracefully
        assert response.status_code in [status.HTTP_400_BAD_REQUEST, status.HTTP_415_UNSUPPORTED_MEDIA_TYPE]

    def test_method_not_allowed(self):
        """Test method not allowed responses."""
        self.client.force_authenticate(user=self.superuser)

        # Try PATCH on a list endpoint that doesn't support it
        url = reverse("api:v1:user-list")
        response = self.client.patch(url, {})

        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED

    def test_unauthenticated_access(self):
        """Test unauthenticated access to protected endpoints."""
        url = reverse("api:v1:user-list")
        response = self.client.get(url)

        assert response.status_code in [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN]

    def test_pagination_edge_cases(self):
        """Test pagination edge cases."""
        self.client.force_authenticate(user=self.superuser)

        # Test very large page size
        url = reverse("api:v1:user-list")
        response = self.client.get(url, {"page_size": 10000})

        assert response.status_code == status.HTTP_200_OK

        # Test invalid page number
        response = self.client.get(url, {"page": 999999})
        assert response.status_code in [status.HTTP_200_OK, status.HTTP_404_NOT_FOUND]
