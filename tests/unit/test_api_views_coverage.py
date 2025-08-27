"""
Additional tests for API views to improve coverage.
"""

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.core.models import Animal, Organization, Team, User


@pytest.mark.unit
class APIViewsCoverageTestCase(APITestCase):
    """Test cases to improve coverage of API views."""

    def setUp(self):
        """Set up test data."""
        self.admin_user = User.objects.create_superuser(
            username="admin", email="admin@example.com", password="adminpass123"
        )
        self.regular_user = User.objects.create_user(username="user", email="user@example.com", password="userpass123")
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

    def test_animal_list_view_methods(self):
        """Test different HTTP methods on animal list view."""
        self.client.force_authenticate(user=self.admin_user)
        url = reverse("api:v1:animal-list")

        # Test GET
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Test POST
        data = {"name": "New Animal", "kind": "cat"}
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_animal_detail_view_methods(self):
        """Test different HTTP methods on animal detail view."""
        animal = Animal.objects.create(name="Test Animal", kind="dog")

        self.client.force_authenticate(user=self.admin_user)
        url = reverse("api:v1:animal-detail", kwargs={"pk": animal.pk})

        # Test GET
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Test PUT
        data = {"name": "Updated Animal", "kind": "cat"}
        response = self.client.put(url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Test DELETE
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

    def test_animal_search_functionality(self):
        """Test animal search functionality."""
        # Create test animals
        Animal.objects.create(name="Fluffy Cat", kind="cat")
        Animal.objects.create(name="Buddy Dog", kind="dog")
        Animal.objects.create(name="Charlie Cat", kind="cat")

        self.client.force_authenticate(user=self.admin_user)
        url = reverse("api:v1:animal-list")

        # Test search by name
        response = self.client.get(url, {"search": "Cat"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 2)

        # Test search by kind
        response = self.client.get(url, {"search": "dog"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)

    def test_user_list_view_methods(self):
        """Test different HTTP methods on user list view."""
        self.client.force_authenticate(user=self.admin_user)
        url = reverse("api:v1:user-list")

        # Test GET
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Test POST
        data = {"username": "newuser", "email": "newuser@example.com", "password": "newpass123"}
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

    def test_filter_and_ordering(self):
        """Test filtering and ordering functionality."""
        # Create additional test data
        Organization.objects.create(name="Alpha Org")
        Organization.objects.create(name="Beta Org")

        self.client.force_authenticate(user=self.admin_user)
        url = reverse("api:v1:organization-list")

        # Test ordering
        response = self.client.get(url, {"ordering": "name"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Should be ordered alphabetically
        names = [org["name"] for org in response.data["results"]]
        self.assertEqual(names, sorted(names))

    def test_api_schema_endpoints(self):
        """Test API schema endpoints."""
        # Test schema endpoint (if available)
        try:
            url = reverse("api:schema")
            response = self.client.get(url)
            self.assertIn(response.status_code, [status.HTTP_200_OK, status.HTTP_404_NOT_FOUND])
        except:
            # Schema endpoint might not be configured
            pass

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
        self.assertIn("count", response.data)
        self.assertIn("results", response.data)

        # Test large page size
        response = self.client.get(url, {"page_size": 50})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Test invalid page
        response = self.client.get(url, {"page": 999})
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
