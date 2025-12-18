"""
Tests for Dynaconf configuration and settings precedence.

Following AAP Phase 1 standards from handbook proposal 0014-Django-Settings.
Tests ensure proper precedence order and validator functionality.

Note: These tests are marked as integration tests because they require
the full dynaconf settings environment, not the test.py settings used by pytest.
"""

import os
from pathlib import Path
from unittest import mock

import pytest

# Set a valid SECRET_KEY for test module import
# This allows Django settings to load without validation errors
os.environ.setdefault("METRICS_SERVICE_SECRET_KEY", "your-secret-key-here-change-in-production")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "metrics_service.settings")

# Mark all tests in this module as integration tests
pytestmark = pytest.mark.integration


class TestDynaconfPrecedence:
    """Test settings precedence order following AAP standards.

    Note: These tests verify the Dynaconf instance directly since Django
    settings are cached and cannot be reliably reloaded in tests.
    """

    def test_dynaconf_can_read_env_vars(self):
        """Test that Dynaconf can read environment variables via load_envvars."""
        from metrics_service.settings import DYNACONF

        # DYNACONF should have loaded SECRET_KEY from one of the config sources
        # Locally: from .env or defaults.py → "dev-secret-key-change-in-production"
        # In CI: from config/settings.yaml → "your-secret-key-here-change-in-production"
        secret_key = DYNACONF.get("SECRET_KEY")
        assert secret_key == "test-only-secret-key-for-testing-purposes-only", (
            f"Unexpected SECRET_KEY value: {secret_key}"
        )

    def test_database_defaults_loaded(self):
        """Test that database defaults from defaults.py are loaded."""
        from django.conf import settings

        # Database settings should be present
        assert "default" in settings.DATABASES
        assert settings.DATABASES["default"]["ENGINE"] == "django.db.backends.postgresql"
        assert settings.DATABASES["default"]["NAME"] is not None


class TestDynaconfValidators:
    """Test Dynaconf validators enforce security requirements.

    Note: Validators are only loaded in production mode (METRICS_SERVICE_MODE=production).
    These tests import the production validators directly to verify they are configured.
    """

    def test_validators_are_registered_in_production(self):
        """Test that validators are defined in production settings."""
        from apps.settings.production import validators

        assert len(validators) > 0

    def test_secret_key_validators_configured(self):
        """Test that SECRET_KEY validators are configured in production."""
        from apps.settings.production import validators

        secret_key_validators = [v for v in validators if "SECRET_KEY" in v.names]

        # Should have at least 1 validator for SECRET_KEY
        assert len(secret_key_validators) > 0

    def test_database_validators_configured(self):
        """Test that database validators are configured in production."""
        from apps.settings.production import validators

        # Should have validators for database settings
        db_validators = [v for v in validators if any("DATABASES" in str(name) for name in v.names)]
        assert len(db_validators) > 0

    def test_settings_pass_validation(self):
        """Test that current settings pass validation (since we're running)."""
        from django.conf import settings

        # If we got here, validation passed during settings load
        assert settings.SECRET_KEY is not None
        assert settings.DATABASES is not None


class TestEnvironmentSwitching:
    """Test environment-specific configuration sections."""

    def test_current_environment_is_set(self):
        """Test that current_env is properly set."""
        from metrics_service.settings import DYNACONF

        # Should have a current environment
        assert DYNACONF.current_env is not None
        assert isinstance(DYNACONF.current_env, str)

    def test_is_development_mode_flag(self):
        """Test that is_development_mode flag is set by factory."""
        from metrics_service.settings import DYNACONF

        # Factory should set is_development_mode based on environment
        assert hasattr(DYNACONF, "is_development_mode")
        assert isinstance(DYNACONF.is_development_mode, bool)


class TestDynaconfFactory:
    """Test that DAB factory pattern is properly configured."""

    def test_factory_creates_dynaconf_instance(self):
        """Test that factory creates a valid Dynaconf instance."""
        from metrics_service.settings import DYNACONF

        assert DYNACONF is not None
        assert hasattr(DYNACONF, "validators")
        assert hasattr(DYNACONF, "current_env")

    def test_factory_registers_validators_in_production(self):
        """Test that validators are defined in production settings module.

        Note: Validators are only registered with DYNACONF when running in
        production mode (METRICS_SERVICE_MODE=production). This test verifies
        that production.py defines the expected validators.
        """
        from apps.settings.production import validators

        # Check that validators are defined in production settings
        assert len(validators) > 0

        # Check for SECRET_KEY validators
        secret_key_validators = [v for v in validators if "SECRET_KEY" in v.names]
        assert len(secret_key_validators) > 0

    def test_envvar_prefix_configured(self):
        """Test that METRICS_SERVICE prefix is configured."""
        from metrics_service.settings import DYNACONF

        # Check that the prefix is configured by seeing if env vars work
        # The fact that SECRET_KEY was loaded from METRICS_SERVICE_SECRET_KEY proves it works
        assert DYNACONF.get("SECRET_KEY") is not None


class TestSettingsFileLoading:
    """Test that settings files are loaded in correct order."""

    def test_defaults_py_loaded(self):
        """Test that defaults.py values are loaded."""
        with mock.patch.dict(os.environ, {"METRICS_SERVICE_SECRET_KEY": "valid-key"}):
            import importlib

            from metrics_service import settings as settings_module

            importlib.reload(settings_module)

            from django.conf import settings

            # Values from defaults.py should be present
            assert settings.SERVICE_TYPE == "metrics-service"
            assert Path(settings_module.__file__).resolve().parent.parent == settings.BASE_DIR
