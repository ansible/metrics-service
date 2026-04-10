"""
Permission tests for SettingViewSet.

Verifies that auditor users (is_system_auditor=True) are denied access to all
mutating actions: update (PUT), partial_update (PATCH), reload (POST), and
rollback (POST).  Read-only access (GET list) is allowed for auditors.
"""

import pytest
from rest_framework.test import APIClient

from apps.core.models import User


def _make_auditor(username="auditor_user"):
    return User.objects.create_user(
        username=username,
        password="testpass123",
        is_system_auditor=True,
    )


@pytest.mark.unit
@pytest.mark.django_db
class TestSettingViewSetAuditorPermissions:
    """Auditor users must be denied all mutating SettingViewSet actions."""

    def setup_method(self):
        self.auditor = _make_auditor()
        self.client = APIClient()
        self.client.force_authenticate(user=self.auditor)

    def test_auditor_cannot_update_settings(self):
        """PUT /api/v1/settings/ must return 403 for an auditor."""
        response = self.client.put("/api/v1/settings/", data={"DEBUG": False}, format="json")
        assert response.status_code == 403

    def test_auditor_cannot_partial_update_settings(self):
        """PATCH /api/v1/settings/ must return 403 for an auditor."""
        response = self.client.patch("/api/v1/settings/", data={"DEBUG": False}, format="json")
        assert response.status_code == 403

    def test_auditor_cannot_reload_settings(self):
        """POST /api/v1/settings/reload/ must return 403 for an auditor."""
        response = self.client.post("/api/v1/settings/reload/")
        assert response.status_code == 403

    def test_auditor_cannot_rollback_settings(self):
        """POST /api/v1/settings/rollback/<id>/ must return 403 for an auditor."""
        response = self.client.post("/api/v1/settings/rollback/1/")
        assert response.status_code == 403
