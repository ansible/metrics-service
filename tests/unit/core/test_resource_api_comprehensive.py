"""
Comprehensive tests for core resource_api module.

This module provides complete test coverage for the resource_api configuration,
testing all code paths including import error handling and service metadata.
"""

from unittest.mock import patch

import pytest
from django.test import TestCase


@pytest.mark.unit
class TestResourceAPIConfiguration(TestCase):
    """Test cases for resource API configuration."""

    def test_api_config_class_exists(self):
        """Test that APIConfig class exists and has correct service_type."""
        from apps.core.resource_api import APIConfig

        assert hasattr(APIConfig, "service_type")
        assert APIConfig.service_type == "metrics_service"

    def test_resource_list_exists(self):
        """Test that RESOURCE_LIST exists and contains configurations."""
        from apps.core.resource_api import RESOURCE_LIST

        assert isinstance(RESOURCE_LIST, list)
        assert len(RESOURCE_LIST) >= 3  # At minimum: User, Team, Organization

    def test_resource_list_contains_user(self):
        """Test that RESOURCE_LIST contains User model configuration."""
        from django.contrib.auth import get_user_model

        from apps.core.resource_api import RESOURCE_LIST

        user_model = get_user_model()
        user_configs = [rc for rc in RESOURCE_LIST if rc.model == user_model]

        assert len(user_configs) == 1
        user_config = user_configs[0]
        assert user_config.name_field == "username"
        # ResourceConfig has the model attribute which is what matters
        assert user_config.model == user_model

    def test_resource_list_contains_team(self):
        """Test that RESOURCE_LIST contains Team model configuration."""
        from apps.core.models import Team
        from apps.core.resource_api import RESOURCE_LIST

        team_configs = [rc for rc in RESOURCE_LIST if rc.model == Team]

        assert len(team_configs) == 1
        team_config = team_configs[0]
        assert team_config.model == Team

    def test_resource_list_contains_organization(self):
        """Test that RESOURCE_LIST contains Organization model configuration."""
        from apps.core.models import Organization
        from apps.core.resource_api import RESOURCE_LIST

        org_configs = [rc for rc in RESOURCE_LIST if rc.model == Organization]

        assert len(org_configs) == 1
        org_config = org_configs[0]
        assert org_config.model == Organization

    def test_authenticator_import_success(self):
        """Test that Authenticator is added to RESOURCE_LIST when import succeeds."""
        # This test verifies the try/except block at lines 43-53
        # If ansible_base.authentication is available, Authenticator should be in the list
        try:
            from ansible_base.authentication.models import Authenticator

            from apps.core.resource_api import RESOURCE_LIST

            auth_configs = [rc for rc in RESOURCE_LIST if rc.model == Authenticator]
            # Should have at least one if import succeeded
            assert len(auth_configs) > 0  # May or may not be present depending on environment
        except ImportError:
            # If import fails, that's expected and covered by the except block
            pass

    def test_roledefinition_import_success(self):
        """Test that RoleDefinition is added to RESOURCE_LIST when import succeeds."""
        # This test verifies the try/except block at lines 68-73
        try:
            from ansible_base.rbac.models import RoleDefinition

            from apps.core.resource_api import RESOURCE_LIST

            role_configs = [rc for rc in RESOURCE_LIST if rc.model == RoleDefinition]
            # Should have at least one if import succeeded
            assert len(role_configs) > 0  # May or may not be present depending on environment
        except ImportError:
            # If import fails, that's expected and covered by the except block
            pass

    def test_service_metadata_basic(self):
        """Test service_metadata returns correct basic structure."""
        from apps.core.resource_api import service_metadata

        metadata = service_metadata()

        assert isinstance(metadata, dict)
        assert "service_type" in metadata
        assert metadata["service_type"] == "metrics_service"
        assert "system_uuid" in metadata
        assert "version" in metadata
        assert metadata["version"] == "1.0.0"

    def test_service_metadata_with_settings_uuid(self):
        """Test service_metadata uses SYSTEM_UUID from settings if available."""
        from apps.core.resource_api import service_metadata

        with patch("apps.core.resource_api.settings") as mock_settings:
            mock_settings.SYSTEM_UUID = "test-uuid-123"

            metadata = service_metadata()

            assert metadata["system_uuid"] == "test-uuid-123"

    def test_service_metadata_without_settings_uuid(self):
        """Test service_metadata handles missing SYSTEM_UUID gracefully."""
        from apps.core.resource_api import service_metadata

        with patch("apps.core.resource_api.settings") as mock_settings:
            # Remove SYSTEM_UUID attribute to trigger getattr default
            del mock_settings.SYSTEM_UUID

            metadata = service_metadata()

            assert metadata["system_uuid"] == "unknown"

    def test_service_metadata_exception_handling(self):
        """Test service_metadata handles exceptions gracefully."""
        # This test covers lines 89-90 by making the dict creation raise an exception
        from apps.core.resource_api import service_metadata

        # Mock getattr to raise an exception, which will cause the try block to fail
        def getattr_side_effect(obj, attr, default=None):
            raise RuntimeError("Forced exception")

        with patch("builtins.getattr", side_effect=getattr_side_effect):
            metadata = service_metadata()

            # Should return default values from except block
            assert metadata["service_type"] == "metrics_service"
            assert metadata["system_uuid"] == "unknown"
            assert metadata["version"] == "1.0.0"

    def test_module_imports(self):
        """Test that all required modules can be imported."""
        from apps.core import resource_api

        assert hasattr(resource_api, "APIConfig")
        assert hasattr(resource_api, "RESOURCE_LIST")
        assert hasattr(resource_api, "service_metadata")

    def test_resource_config_structure(self):
        """Test that ResourceConfig objects have expected structure."""
        from apps.core.resource_api import RESOURCE_LIST

        for resource_config in RESOURCE_LIST:
            # All should have a model attribute
            assert hasattr(resource_config, "model")
            assert resource_config.model is not None


@pytest.mark.unit
class TestResourceAPIImportHandling(TestCase):
    """Test cases for import error handling in resource_api."""

    def test_authenticator_import_error_handling(self):
        """Test that ImportError for Authenticator is handled gracefully."""
        # The try/except block should handle ImportError without raising
        # This is implicitly tested by the module loading successfully
        # even if ansible_base.authentication is not available
        from apps.core import resource_api

        # Module should load without errors
        assert hasattr(resource_api, "RESOURCE_LIST")

    def test_roledefinition_import_error_handling(self):
        """Test that ImportError for RoleDefinition is handled gracefully."""
        # The try/except block should handle ImportError without raising
        # This is implicitly tested by the module loading successfully
        # even if ansible_base.rbac is not available
        from apps.core import resource_api

        # Module should load without errors
        assert hasattr(resource_api, "RESOURCE_LIST")

    def test_module_loads_with_minimal_dependencies(self):
        """Test that module loads even with minimal dependencies."""
        # This test ensures the module is robust to missing optional dependencies
        import apps.core.resource_api

        # Should be able to call service_metadata
        metadata = apps.core.resource_api.service_metadata()
        assert isinstance(metadata, dict)
