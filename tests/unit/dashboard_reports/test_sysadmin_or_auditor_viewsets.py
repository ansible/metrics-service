"""
Unit tests for admin base viewsets.

Tests that BaseAdminViewSet and GenericAdminViewSet correctly enforce
the IsSystemAdminOrAuditor permission class.
"""

from unittest.mock import MagicMock, patch

import pytest

from apps.dashboard_reports.viewsets.admin_viewsets import BaseAdminViewSet, GenericAdminViewSet


@pytest.mark.unit
class TestBaseAdminViewSet:
    """Tests for BaseAdminViewSet permission configuration."""

    def test_has_is_system_admin_or_auditor_permission(self) -> None:
        """IsSystemAdminOrAuditor must be in permission_classes."""
        from ansible_base.rbac.api.permissions import IsSystemAdminOrAuditor

        assert IsSystemAdminOrAuditor in BaseAdminViewSet.permission_classes

    def test_permission_classes_contains_exactly_one_class(self) -> None:
        """permission_classes should contain exactly one entry."""
        assert len(BaseAdminViewSet.permission_classes) == 1

    def test_get_permissions_returns_is_system_admin_or_auditor_instance(self) -> None:
        """get_permissions() must return an IsSystemAdminOrAuditor instance."""
        from ansible_base.rbac.api.permissions import IsSystemAdminOrAuditor

        viewset = BaseAdminViewSet()
        permissions = viewset.get_permissions()

        assert len(permissions) == 1
        assert isinstance(permissions[0], IsSystemAdminOrAuditor)


@pytest.mark.unit
class TestGenericAdminViewSet:
    """Tests for GenericAdminViewSet permission configuration."""

    def test_has_is_system_admin_or_auditor_permission(self) -> None:
        """IsSystemAdminOrAuditor must be in permission_classes."""
        from ansible_base.rbac.api.permissions import IsSystemAdminOrAuditor

        assert IsSystemAdminOrAuditor in GenericAdminViewSet.permission_classes

    def test_permission_classes_contains_exactly_one_class(self) -> None:
        """permission_classes should contain exactly one entry."""
        assert len(GenericAdminViewSet.permission_classes) == 1

    def test_get_permissions_returns_is_system_admin_or_auditor_instance(self) -> None:
        """get_permissions() must return an IsSystemAdminOrAuditor instance."""
        from ansible_base.rbac.api.permissions import IsSystemAdminOrAuditor

        viewset = GenericAdminViewSet()
        permissions = viewset.get_permissions()

        assert len(permissions) == 1
        assert isinstance(permissions[0], IsSystemAdminOrAuditor)


@pytest.mark.unit
class TestBaseAdminViewSetPermissionEnforcement:
    """Tests that permission checks behave correctly for BaseAdminViewSet subclasses."""

    def setup_method(self) -> None:
        self.viewset = BaseAdminViewSet()
        self.request = MagicMock()
        self.view = MagicMock()

    def test_system_admin_has_permission(self) -> None:
        """System admin (has_super_permission=True) must be granted access."""
        with patch("ansible_base.rbac.api.permissions.has_super_permission", return_value=True):
            self.request.user.is_authenticated = True
            self.request.method = "GET"

            permission = self.viewset.get_permissions()[0]
            result = permission.has_permission(self.request, self.view)

        assert result is True

    def test_non_admin_authenticated_user_write_is_denied(self) -> None:
        """Non-admin authenticated user must be denied write access."""
        with patch("ansible_base.rbac.api.permissions.has_super_permission", return_value=False):
            self.request.user.is_authenticated = True
            self.request.method = "POST"

            permission = self.viewset.get_permissions()[0]
            result = permission.has_permission(self.request, self.view)

        assert result is False

    def test_unauthenticated_user_is_denied(self) -> None:
        """Unauthenticated users must always be denied."""
        self.request.user = None

        permission = self.viewset.get_permissions()[0]
        result = permission.has_permission(self.request, self.view)

        assert result is False


@pytest.mark.unit
class TestGenericAdminViewSetPermissionEnforcement:
    """Tests that permission checks behave correctly for GenericAdminViewSet subclasses."""

    def setup_method(self) -> None:
        self.viewset = GenericAdminViewSet()
        self.request = MagicMock()
        self.view = MagicMock()

    def test_system_admin_has_permission(self) -> None:
        """System admin (has_super_permission=True) must be granted access."""
        with patch("ansible_base.rbac.api.permissions.has_super_permission", return_value=True):
            self.request.user.is_authenticated = True
            self.request.method = "GET"

            permission = self.viewset.get_permissions()[0]
            result = permission.has_permission(self.request, self.view)

        assert result is True

    def test_non_admin_authenticated_user_write_is_denied(self) -> None:
        """Non-admin authenticated user must be denied write access."""
        with patch("ansible_base.rbac.api.permissions.has_super_permission", return_value=False):
            self.request.user.is_authenticated = True
            self.request.method = "POST"

            permission = self.viewset.get_permissions()[0]
            result = permission.has_permission(self.request, self.view)

        assert result is False

    def test_unauthenticated_user_is_denied(self) -> None:
        """Unauthenticated users must always be denied."""
        self.request.user = None

        permission = self.viewset.get_permissions()[0]
        result = permission.has_permission(self.request, self.view)

        assert result is False


@pytest.mark.unit
class TestAdminViewSetInheritance:
    """Tests for correct inheritance of admin viewsets."""

    def test_base_admin_viewset_inherits_from_base_viewset(self) -> None:
        """BaseAdminViewSet must inherit from ViewSet."""
        from rest_framework.viewsets import ViewSet

        assert issubclass(BaseAdminViewSet, ViewSet)

    def test_generic_admin_viewset_inherits_from_generic_viewset(self) -> None:
        """GenericAdminViewSet must inherit from GenericViewSet."""
        from rest_framework.viewsets import GenericViewSet

        assert issubclass(GenericAdminViewSet, GenericViewSet)

    def test_subclass_inherits_permission_classes(self) -> None:
        """A concrete subclass must inherit permission_classes unchanged."""
        from ansible_base.rbac.api.permissions import IsSystemAdminOrAuditor

        class MyAdminViewSet(BaseAdminViewSet):
            pass

        assert IsSystemAdminOrAuditor in MyAdminViewSet.permission_classes

    def test_subclass_can_override_permission_classes(self) -> None:
        """A concrete subclass must be able to override permission_classes."""
        from rest_framework.permissions import AllowAny

        class MyAdminViewSet(BaseAdminViewSet):
            permission_classes = [AllowAny]

        assert AllowAny in MyAdminViewSet.permission_classes
        assert len(MyAdminViewSet.permission_classes) == 1
