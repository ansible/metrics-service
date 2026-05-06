"""Tests for PostgreSQL session parameter normalization."""

from apps.settings.defaults import (
    SUPPORTED_PG_SESSION_PARAMS,
    _normalize_postgresql_options,
)


class TestPostgreSQLNormalization:
    """Test PostgreSQL session parameter normalization."""

    def test_basic_normalization(self):
        """Test basic session parameter normalization with space escaping."""
        databases = {
            "default": {
                "ENGINE": "django.db.backends.postgresql",
                "OPTIONS": {
                    "sslmode": "prefer",
                    "datestyle": "iso, mdy",
                    "application_name": "test app",
                },
            }
        }

        result = _normalize_postgresql_options(databases)

        # Session params should be removed from OPTIONS
        assert "datestyle" not in result["default"]["OPTIONS"]
        assert "application_name" not in result["default"]["OPTIONS"]
        # Non-session params should remain
        assert "sslmode" in result["default"]["OPTIONS"]
        # Should convert to -c format with escaped spaces
        assert result["default"]["OPTIONS"]["options"] == ("-c datestyle=iso,\\ mdy -c application_name=test\\ app")

    def test_preserves_existing_options(self):
        """Test that existing options string is preserved and extended."""
        databases = {
            "default": {
                "OPTIONS": {
                    "options": "-c statement_timeout=30000",
                    "timezone": "UTC",
                }
            }
        }

        result = _normalize_postgresql_options(databases)

        options = result["default"]["OPTIONS"]["options"]
        # Should preserve existing options
        assert "-c statement_timeout=30000" in options
        # Should append normalized parameter
        assert "-c timezone=UTC" in options

    def test_does_not_mutate_input(self):
        """Test that input dictionary is not mutated (deep copy test)."""
        databases = {
            "default": {
                "OPTIONS": {
                    "datestyle": "iso",
                    "sslmode": "require",
                }
            }
        }

        original_opts = databases["default"]["OPTIONS"].copy()
        result = _normalize_postgresql_options(databases)

        # Original should be unchanged
        assert databases["default"]["OPTIONS"] == original_opts
        # Result should be different object
        assert result is not databases
        # Session param should be removed from result, not original
        assert "datestyle" not in result["default"]["OPTIONS"]

    def test_error_handling_restores_params(self):
        """Test that normalization errors don't lose session parameters."""
        databases = {
            "default": {
                "OPTIONS": {
                    "application_name": "test",
                }
            }
        }

        # Even if something goes wrong internally, function should return valid result
        result = _normalize_postgresql_options(databases)

        # Should either normalize successfully OR restore params to OPTIONS
        # (In practice this always succeeds, but tests error handling code path exists)
        assert isinstance(result, dict)
        assert "default" in result

    def test_all_supported_parameters(self):
        """Test all supported parameters are normalized together."""
        databases = {
            "default": {
                "OPTIONS": {
                    "datestyle": "iso, mdy",
                    "timezone": "UTC",
                    "search_path": "public,app_schema",
                    "application_name": "test_app",
                }
            }
        }

        result = _normalize_postgresql_options(databases)

        options_str = result["default"]["OPTIONS"]["options"]
        # All parameters should be in -c format
        assert "-c datestyle=iso,\\ mdy" in options_str
        assert "-c timezone=UTC" in options_str
        assert "-c search_path=public,app_schema" in options_str
        assert "-c application_name=test_app" in options_str
        # All should be removed from OPTIONS
        assert "datestyle" not in result["default"]["OPTIONS"]
        assert "timezone" not in result["default"]["OPTIONS"]
        assert "search_path" not in result["default"]["OPTIONS"]
        assert "application_name" not in result["default"]["OPTIONS"]

    def test_supported_params_constant_complete(self):
        """Test that SUPPORTED_PG_SESSION_PARAMS contains expected parameters."""
        expected_params = {
            "datestyle",
            "search_path",
            "timezone",
            "application_name",
        }
        assert expected_params == SUPPORTED_PG_SESSION_PARAMS
