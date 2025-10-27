"""
Unit tests for Setting API views.
"""

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from apps.core.models import Setting

User = get_user_model()


@pytest.mark.unit
class TestSettingViewSet(APITestCase):
    """Test cases for SettingView."""

    def setUp(self):
        """Set up test data."""
        self.client = APIClient()
        self.admin = User.objects.create_superuser(username="admin", email="admin@example.com", password="admin123")

    def test_update_config(self):
        """Test updating config via API."""
        self.client.force_authenticate(user=self.admin)
        url = reverse("api:v1:settings-update-config")
        data = {"TEST_SETTING": "test value"}
        response = self.client.put(url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        # Verify setting was created
        setting = Setting.objects.get(setting_key="TEST_SETTING")
        self.assertIsNotNone(setting)

    def test_rollback(self):
        """Test rollback endpoint."""
        # Create a setting first
        setting = Setting.objects.create(
            setting_key="TEST",
            current_value='"new"',
            previous_value='"old"',
            last_modified_by=self.admin,
            source="api",
        )

        self.client.force_authenticate(user=self.admin)
        url = reverse("api:v1:settings-rollback", kwargs={"change_id": setting.id})
        response = self.client.post(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("success", response.data)
