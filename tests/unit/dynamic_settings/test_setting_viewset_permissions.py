"""
Permission tests for SettingViewSet.

IsSystemAdminOrAuditor allows writes only to system admins and reads only to system
auditors/admins.  In the test DAB configuration (ANSIBLE_BASE_BYPASS_SUPERUSER_FLAGS
= ["is_superuser"]), any non-superuser user has no super-permission and must receive
403 on all mutating SettingViewSet actions: update (PUT), partial_update (PATCH),
reload (POST), and rollback (POST).

Note: DAB's auditor status is assigned via the sys_auditor global RBAC role (not a
model field).  A plain non-superuser in test settings behaves identically to an
auditor-without-write-access for permission testing purposes.
"""

import pytest
from rest_framework.test import APIClient

from apps.core.models import User


def _make_non_admin(username="non_admin_user"):
    return User.objects.create_user(
        username=username,
        password="testpass123",
        is_superuser=False,
    )


@pytest.mark.unit
@pytest.mark.django_db
class TestSettingViewSetAuditorPermissions:
    """Non-admin users must be denied all mutating SettingViewSet actions."""

    def setup_method(self):
        self.user = _make_non_admin()
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_non_admin_cannot_update_settings(self):
        """PUT /api/v1/settings/ must return 403 for a non-admin user."""
        response = self.client.put("/api/v1/settings/", data={"DEBUG": False}, format="json")
        assert response.status_code == 403

    def test_non_admin_cannot_partial_update_settings(self):
        """PATCH /api/v1/settings/ must return 403 for a non-admin user."""
        response = self.client.patch("/api/v1/settings/", data={"DEBUG": False}, format="json")
        assert response.status_code == 403

    def test_non_admin_cannot_reload_settings(self):
        """POST /api/v1/settings/reload/ must return 403 for a non-admin user."""
        response = self.client.post("/api/v1/settings/reload/")
        assert response.status_code == 403

    def test_non_admin_cannot_rollback_settings(self):
        """POST /api/v1/settings/rollback/<id>/ must return 403 for a non-admin user."""
        response = self.client.post("/api/v1/settings/rollback/1/")
        assert response.status_code == 403
