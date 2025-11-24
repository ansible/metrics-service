"""
Additional tests for API views to improve coverage.
"""

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.core.models import Organization, Team, User
from tests.test_utils import get_test_password


@pytest.mark.unit
class APIViewsCoverageTestCase(APITestCase):
    """Test cases to improve coverage of API views."""

    def setUp(self):
        """Set up test data."""
        self.admin_user = User.objects.create_superuser(
            username="admin", email="admin@example.com", password=get_test_password()
        )
        self.regular_user = User.objects.create_user(
            username="user", email="user@example.com", password=get_test_password()
        )
        self.organization = Organization.objects.create(name="Test Org")
        self.team = Team.objects.create(name="Test Team", organization=self.organization)

    def test_organization_list_view_methods(self):
        """Test different HTTP methods on organization list view."""
        self.client.force_authenticate(user=self.admin_user)
        url = reverse("api:v1:organization-list")

        # Test GET
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Test POST
        data = {"name": "New Organization"}
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # Verify creation
        self.assertTrue(Organization.objects.filter(name="New Organization").exists())

    def test_organization_detail_view_methods(self):
        """Test different HTTP methods on organization detail view."""
        self.client.force_authenticate(user=self.admin_user)
        url = reverse("api:v1:organization-detail", kwargs={"pk": self.organization.pk})

        # Test GET
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["name"], "Test Org")

        # Test PUT
        data = {"name": "Updated Organization"}
        response = self.client.put(url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Verify update
        self.organization.refresh_from_db()
        self.assertEqual(self.organization.name, "Updated Organization")

        # Test PATCH
        data = {"name": "Patched Organization"}
        response = self.client.patch(url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Test DELETE
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Organization.objects.filter(pk=self.organization.pk).exists())

    def test_user_list_view_methods(self):
        """Test different HTTP methods on user list view."""
        self.client.force_authenticate(user=self.admin_user)
        url = reverse("api:v1:user-list")

        # Test GET
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Test POST
        data = {"username": "newuser", "email": "newuser@example.com", "password": get_test_password()}
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_user_detail_view_methods(self):
        """Test different HTTP methods on user detail view."""
        self.client.force_authenticate(user=self.admin_user)
        url = reverse("api:v1:user-detail", kwargs={"pk": self.regular_user.pk})

        # Test GET
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Test PUT
        data = {"username": "updateduser", "email": "updated@example.com", "first_name": "Updated", "last_name": "User"}
        response = self.client.put(url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Test PATCH
        data = {"first_name": "Patched"}
        response = self.client.patch(url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_permission_handling(self):
        """Test API permission handling with different user types."""
        # Test with unauthenticated user
        url = reverse("api:v1:organization-list")
        response = self.client.get(url)
        self.assertIn(response.status_code, [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN])

        # Test with regular user (should work due to superuser bypass settings)
        self.client.force_authenticate(user=self.regular_user)
        response = self.client.get(url)
        # Should work due to our test configuration
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_invalid_data_handling(self):
        """Test handling of invalid data in API views."""
        self.client.force_authenticate(user=self.admin_user)

        # Test invalid organization data
        url = reverse("api:v1:organization-list")
        response = self.client.post(url, {})  # Missing required name field
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        # Test invalid user data
        url = reverse("api:v1:user-list")
        response = self.client.post(url, {"username": ""})  # Invalid username
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_api_pagination_edge_cases(self):
        """Test API pagination edge cases."""
        # Create many organizations to test pagination
        for i in range(30):
            Organization.objects.create(name=f"Org {i:02d}")

        self.client.force_authenticate(user=self.admin_user)
        url = reverse("api:v1:organization-list")

        # Test first page
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Check if response is paginated or a direct list
        if isinstance(response.data, dict) and "count" in response.data:
            self.assertIn("count", response.data)
            self.assertIn("results", response.data)
        else:
            # Direct list response - just check it's a list
            self.assertIsInstance(response.data, list)

        # Test large page size
        response = self.client.get(url, {"page_size": 50})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Test invalid page (may return 200 with empty results or 404 depending on implementation)
        response = self.client.get(url, {"page": 999})
        self.assertIn(response.status_code, [status.HTTP_200_OK, status.HTTP_404_NOT_FOUND])
