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
from dynaconf import Dynaconf
from dynaconf.validator import ValidationError

# Set a valid SECRET_KEY for test module import (test-only; not used in production)
# Prefer TEST_SECRET_KEY env var when running SAST or in CI to avoid hardcoded-secret findings
os.environ.setdefault(
    "METRICS_SERVICE_SECRET_KEY",
    os.getenv("TEST_SECRET_KEY", "test-dynaconf-bootstrap-no-production-use"),
)
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

        # DYNACONF should have loaded SECRET_KEY from Django's auto-generated
        # development key, environment variables, or config files.
        # In tests, without explicit env var, Django generates a default key.
        secret_key = DYNACONF.get("SECRET_KEY")

        # Just verify it exists and is a non-empty string
        assert secret_key is not None, "SECRET_KEY should be set"
        assert isinstance(secret_key, str), "SECRET_KEY should be a string"
        assert len(secret_key) > 0, "SECRET_KEY should not be empty"

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

    @staticmethod
    def _database_settings(**options):
        settings = Dynaconf(environments=True, env="production")
        settings.set("DATABASES__default__PASSWORD", "")
        for name, value in options.items():
            settings.set(f"DATABASES__default__OPTIONS__{name}", value)
        return settings

    def test_database_password_is_optional_with_client_certificate(self):
        """A complete PostgreSQL client certificate configuration needs no password."""
        from apps.settings.production import validators

        settings = self._database_settings(sslcert="/etc/metrics/client.crt", sslkey="/etc/metrics/client.key")
        client_certificate_validator = next(
            validator
            for validator in validators
            if validator.names
            == (
                "DATABASES__default__OPTIONS__sslcert",
                "DATABASES__default__OPTIONS__sslkey",
            )
        )
        password_validator = next(
            validator for validator in validators if validator.names == ("DATABASES__default__PASSWORD",)
        )

        client_certificate_validator.validate(settings)
        password_validator.validate(settings)

    @pytest.mark.parametrize(
        "options",
        ({}, {"sslcert": "/etc/metrics/client.crt"}, {"sslkey": "/etc/metrics/client.key"}),
    )
    def test_database_password_is_required_without_complete_client_certificate(self, options):
        """Passwordless startup is rejected unless both client certificate settings exist."""
        from apps.settings.production import validators

        settings = self._database_settings(**options)
        password_validator = next(
            validator for validator in validators if validator.names == ("DATABASES__default__PASSWORD",)
        )

        with pytest.raises(ValidationError, match="DATABASES__default__PASSWORD must be set"):
            password_validator.validate(settings)

    def test_cert_pair_validator_skipped_for_password_only_config(self):
        """Cert-pair validator must not fire when no cert keys are present (password-auth deployments)."""
        from apps.settings.production import validators

        settings = self._database_settings()
        client_certificate_validator = next(
            validator
            for validator in validators
            if validator.names
            == (
                "DATABASES__default__OPTIONS__sslcert",
                "DATABASES__default__OPTIONS__sslkey",
            )
        )
        # Should not raise — cert-pair validator must be skipped when neither sslcert nor sslkey is set
        client_certificate_validator.validate(settings)

    @pytest.mark.parametrize(
        "options",
        ({"sslcert": "/etc/metrics/client.crt"}, {"sslkey": "/etc/metrics/client.key"}),
    )
    def test_partial_client_certificate_configuration_is_rejected(self, options):
        """Client certificate authentication requires both certificate and key settings."""
        from apps.settings.production import validators

        settings = self._database_settings(**options)
        client_certificate_validator = next(
            validator
            for validator in validators
            if validator.names
            == (
                "DATABASES__default__OPTIONS__sslcert",
                "DATABASES__default__OPTIONS__sslkey",
            )
        )

        with pytest.raises(
            ValidationError, match="sslcert and DATABASES__default__OPTIONS__sslkey must be set together"
        ):
            client_certificate_validator.validate(settings)

    def test_required_production_settings_have_validators(self):
        """Test that required production settings have validators.

        RESOURCE_SERVER__SECRET_KEY, ANSIBLE_BASE_JWT_KEY, SEGMENT_WRITE_KEY, and
        ALLOWED_HOSTS are now required in production to ensure proper AAP gateway
        integration and prevent misconfigured deployments.

        SEGMENT_WRITE_KEY is baked into the container image at build time, so it
        should always be present even in air-gapped environments.
        """
        from apps.settings.production import validators

        required_settings = {
            "RESOURCE_SERVER__SECRET_KEY",
            "ANSIBLE_BASE_JWT_KEY",
            "SEGMENT_WRITE_KEY",
            "ALLOWED_HOSTS",
        }

        found_validators = set()
        for v in validators:
            for name in v.names:
                if name in required_settings:
                    found_validators.add(name)

        # All required settings should have validators
        assert found_validators == required_settings, f"Missing validators for: {required_settings - found_validators}"

    def test_settings_pass_validation(self):
        """Test that current settings pass validation (since we're running)."""
        from django.conf import settings

        # If we got here, validation passed during settings load
        assert settings.SECRET_KEY is not None
        assert settings.DATABASES is not None


class TestDatabaseAuthValidation:
    """Validate all database rules together, including independent AWX credentials."""

    @staticmethod
    def _settings(alias, password, options):
        from apps.settings.production import validators

        databases = {
            name: {"HOST": "db.example.com", "USER": "metrics", "PASSWORD": "test-only", "OPTIONS": {}}
            for name in ("default", "awx")
        }
        databases[alias].update(PASSWORD=password, OPTIONS=options)
        settings = Dynaconf(environments=True, env="production", envvar_prefix="PR428_TEST", DATABASES=databases)
        settings.validators.register(
            *(validator for validator in validators if any(name.startswith("DATABASES") for name in validator.names))
        )
        return settings

    @pytest.mark.parametrize("alias", ["default", "awx"])
    @pytest.mark.parametrize(
        ("password", "options", "error"),
        [
            ("test-only", {}, None),
            ("", {}, "PASSWORD must be set"),
            ("", {"sslcert": "/client.crt", "sslkey": "/client.key", "sslmode": "require"}, None),
            ("", {"sslcert": "/client.crt"}, "must be set together"),
            ("", {"sslkey": "/client.key"}, "must be set together"),
            ("test-only", {"sslcert": "/client.crt", "sslkey": "/client.key", "sslmode": "verify-full"}, None),
            ("test-only", {"sslcert": "/client.crt"}, "must be set together"),
            ("test-only", {"sslkey": "/client.key"}, "must be set together"),
            ("", {"sslcert": "", "sslkey": ""}, "PASSWORD must be set"),
            ("test-only", {"sslcert": "/client.crt", "sslkey": None}, "must be set together"),
        ],
    )
    def test_database_auth_matrix(self, alias, password, options, error):
        settings = self._settings(alias, password, options)
        if error:
            with pytest.raises(ValidationError, match=error):
                settings.validators.validate()
        else:
            settings.validators.validate()

    @pytest.mark.parametrize("alias", ["default", "awx"])
    @pytest.mark.parametrize("password", ["", "test-only"])
    @pytest.mark.parametrize("sslmode", [None, "disable", "allow", "prefer", "require", "verify-ca", "verify-full"])
    def test_certificates_require_tls(self, alias, password, sslmode):
        options = {"sslcert": "/client.crt", "sslkey": "/client.key"}
        if sslmode is not None:
            options["sslmode"] = sslmode
        settings = self._settings(alias, password, options)
        if sslmode in ("require", "verify-ca", "verify-full"):
            settings.validators.validate()
        else:
            with pytest.raises(ValidationError, match="sslmode must be require, verify-ca or verify-full"):
                settings.validators.validate()

    @pytest.mark.parametrize("alias", ["default", "awx"])
    @pytest.mark.parametrize("key", ["SSLCERT", "SSLKEY", "SSLMODE", "SSLROOTCERT"])
    def test_uppercase_environment_option_rejected(self, monkeypatch, alias, key):
        monkeypatch.setenv(f"PR428_TEST_DATABASES__{alias}__OPTIONS__{key}", "/configured/value")
        settings = self._settings(alias, "", {})
        assert key in dict(settings.DATABASES[alias]["OPTIONS"])
        with pytest.raises(ValidationError, match="OPTIONS keys must be lowercase"):
            settings.validators.validate()

    def test_both_databases_can_use_certificates_without_passwords(self):
        options = {"sslcert": "/client.crt", "sslkey": "/client.key", "sslmode": "verify-full"}
        settings = self._settings("default", "", options)
        settings.set("DATABASES__awx__PASSWORD", "")
        settings.set("DATABASES__awx__OPTIONS", options)
        settings.validators.validate()


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
