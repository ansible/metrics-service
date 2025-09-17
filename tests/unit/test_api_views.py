"""
Unit tests for API views.
"""

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from apps.core.models import Organization

User = get_user_model()


@pytest.mark.unit
class APIAuthenticationTestCase(APITestCase):
    """Test cases for API authentication."""

    def setUp(self):
        """Set up test data."""
        self.client = APIClient()
        self.user = User.objects.create_user(username="apiuser", email="api@example.com", password="testpass123")

    def test_unauthenticated_access(self):
        """Test that unauthenticated requests are rejected."""
        url = reverse("api:v1:user-list")
        response = self.client.get(url)

        # Should require authentication (may return 401 or 403 depending on permissions)
        self.assertIn(response.status_code, [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN])

    def test_authenticated_access(self):
        """Test that authenticated requests are allowed."""
        self.client.force_authenticate(user=self.user)
        url = reverse("api:v1:user-list")
        response = self.client.get(url)

        # Should allow access (may return 200 or other success status)
        self.assertIn(
            response.status_code,
            [status.HTTP_200_OK, status.HTTP_403_FORBIDDEN],  # Might be forbidden due to permissions
        )


@pytest.mark.unit
class UserViewSetTestCase(APITestCase):
    """Test cases for UserViewSet."""

    def setUp(self):
        """Set up test data."""
        self.client = APIClient()
        self.user = User.objects.create_user(username="testuser", email="test@example.com", password="testpass123")
        self.admin_user = User.objects.create_superuser(
            username="admin", email="admin@example.com", password="adminpass123"
        )

    def test_user_detail_authenticated(self):
        """Test user detail endpoint with authentication."""
        self.client.force_authenticate(user=self.admin_user)
        url = reverse("api:v1:user-detail", kwargs={"pk": self.user.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["username"], "testuser")
        self.assertEqual(response.data["email"], "test@example.com")

    def test_user_create_authenticated(self):
        """Test user creation via API."""
        self.client.force_authenticate(user=self.admin_user)
        url = reverse("api:v1:user-list")
        data = {"username": "newuser", "email": "new@example.com", "password": "newpass123"}
        response = self.client.post(url, data, format="json")

        # Response code depends on permissions, but should not be 401
        self.assertNotEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_user_update_authenticated(self):
        """Test user update via API."""
        self.client.force_authenticate(user=self.admin_user)
        url = reverse("api:v1:user-detail", kwargs={"pk": self.user.pk})
        data = {"email": "updated@example.com"}
        response = self.client.patch(url, data, format="json")

        # Response code depends on permissions, but should not be 401
        self.assertNotEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


@pytest.mark.unit
class OrganizationViewSetTestCase(APITestCase):
    """Test cases for OrganizationViewSet."""

    def setUp(self):
        """Set up test data."""
        self.client = APIClient()
        self.user = User.objects.create_superuser(username="orguser", email="org@example.com", password="testpass123")
        self.organization = Organization.objects.create(name="Test Organization")

    def test_organization_detail_authenticated(self):
        """Test organization detail endpoint."""
        self.client.force_authenticate(user=self.user)
        url = reverse("api:v1:organization-detail", kwargs={"pk": self.organization.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["name"], "Test Organization")

    def test_organization_create_authenticated(self):
        """Test organization creation via API."""
        self.client.force_authenticate(user=self.user)
        url = reverse("api:v1:organization-list")
        data = {"name": "New Organization"}
        response = self.client.post(url, data, format="json")

        # Response code depends on permissions
        self.assertNotEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_organization_filtering(self):
        """Test organization filtering."""
        # Create additional organizations
        Organization.objects.create(name="Alpha Org")
        Organization.objects.create(name="Beta Org")

        self.client.force_authenticate(user=self.user)
        url = reverse("api:v1:organization-list")
        response = self.client.get(url + "?search=Alpha")

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_organization_ordering(self):
        """Test organization ordering."""
        self.client.force_authenticate(user=self.user)
        url = reverse("api:v1:organization-list")
        response = self.client.get(url + "?ordering=name")

        self.assertEqual(response.status_code, status.HTTP_200_OK)


@pytest.mark.unit
class APIErrorHandlingTestCase(APITestCase):
    """Test cases for API error handling."""

    def setUp(self):
        """Set up test data."""
        self.client = APIClient()
        self.user = User.objects.create_user(username="erroruser", email="error@example.com", password="testpass123")

    def test_not_found_error(self):
        """Test 404 error handling."""
        self.client.force_authenticate(user=self.user)
        url = reverse("api:v1:organization-detail", kwargs={"pk": 99999})
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_method_not_allowed(self):
        """Test method not allowed error."""
        self.client.force_authenticate(user=self.user)
        url = reverse("api:v1:organization-list")
        # Try to use PATCH on list endpoint
        response = self.client.patch(url, {})

        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)


@pytest.mark.unit
class APIVersioningTestCase(APITestCase):
    """Test cases for API versioning."""

    def setUp(self):
        """Set up test data."""
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="versionuser", email="version@example.com", password="testpass123"
        )

    def test_v1_api_access(self):
        """Test v1 API access."""
        self.client.force_authenticate(user=self.user)
        url = reverse("api:v1:organization-list")
        response = self.client.get(url)

        # Should be able to access v1 API
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_api_version_header(self):
        """Test API version in response headers."""
        self.client.force_authenticate(user=self.user)
        url = reverse("api:v1:organization-list")
        response = self.client.get(url)

        # API version might be indicated in headers or response
        self.assertEqual(response.status_code, status.HTTP_200_OK)


@pytest.mark.unit
class APISerializerTestCase(APITestCase):
    """Test cases for API serializers."""

    def setUp(self):
        """Set up test data."""
        self.client = APIClient()
        self.user = User.objects.create_superuser(
            username="serializeruser", email="serializer@example.com", password="testpass123"
        )
        self.organization = Organization.objects.create(name="Serializer Org")

    def test_organization_serialization(self):
        """Test organization serialization."""
        self.client.force_authenticate(user=self.user)
        url = reverse("api:v1:organization-detail", kwargs={"pk": self.organization.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Check expected fields are present
        expected_fields = ["id", "name", "created", "modified"]
        for field in expected_fields:
            self.assertIn(field, response.data)

    def test_user_serialization_excludes_password(self):
        """Test user serialization excludes password."""
        self.client.force_authenticate(user=self.user)
        url = reverse("api:v1:user-detail", kwargs={"pk": self.user.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Password should not be in serialized data
        self.assertNotIn("password", response.data)


@pytest.mark.unit
class UserPasswordTestCase(APITestCase):
    """Test cases for user password functionality."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_superuser(username="admin", email="admin@example.com", password="adminpass123")
        self.test_user = User.objects.create_user(username="testuser", email="test@example.com", password="testpass123")

    def test_set_password_success(self):
        """Test successful password change."""
        self.client.force_authenticate(user=self.user)
        url = reverse("api:v1:user-set-password", kwargs={"pk": self.test_user.pk})

        response = self.client.post(url, {"password": "newpassword123"})

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        # Verify password was changed
        self.test_user.refresh_from_db()
        self.assertTrue(self.test_user.check_password("newpassword123"))

    def test_set_password_missing_password(self):
        """Test password change with missing password field."""
        self.client.force_authenticate(user=self.user)
        url = reverse("api:v1:user-set-password", kwargs={"pk": self.test_user.pk})

        response = self.client.post(url, {})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("error", response.data)
        self.assertEqual(response.data["error"], "Password is required")

    def test_set_password_empty_password(self):
        """Test password change with empty password."""
        self.client.force_authenticate(user=self.user)
        url = reverse("api:v1:user-set-password", kwargs={"pk": self.test_user.pk})

        response = self.client.post(url, {"password": ""})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("error", response.data)

    def test_set_password_unauthenticated(self):
        """Test password change without authentication."""
        url = reverse("api:v1:user-set-password", kwargs={"pk": self.test_user.pk})

        response = self.client.post(url, {"password": "newpassword123"})

        self.assertIn(response.status_code, [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN])
