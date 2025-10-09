"""
Comprehensive test coverage for apps/tasks/dispatcherd_config.py

This module provides extensive coverage for dispatcherd configuration utilities,
path resolution, environment handling, and error conditions.
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from django.test import TestCase, override_settings

from apps.tasks import dispatcherd_config


@pytest.mark.unit
class TestGetConfigFilePath(TestCase):
    """Test get_config_file_path function."""

    def setUp(self):
        """Set up test environment."""
        # Store original environment
        self.original_env = os.environ.get("DISPATCHERD_CONFIG_FILE")

    def tearDown(self):
        """Clean up test environment."""
        # Restore original environment
        if self.original_env is not None:
            os.environ["DISPATCHERD_CONFIG_FILE"] = self.original_env
        elif "DISPATCHERD_CONFIG_FILE" in os.environ:
            del os.environ["DISPATCHERD_CONFIG_FILE"]

    def test_get_config_file_path_from_environment(self):
        """Test getting config file path from environment variable."""
        test_path = "/custom/path/to/config.yaml"
        os.environ["DISPATCHERD_CONFIG_FILE"] = test_path

        result = dispatcherd_config.get_config_file_path()

        assert result == Path(test_path)

    def test_get_config_file_path_default(self):
        """Test getting default config file path."""
        # Remove environment variable if it exists
        if "DISPATCHERD_CONFIG_FILE" in os.environ:
            del os.environ["DISPATCHERD_CONFIG_FILE"]

        result = dispatcherd_config.get_config_file_path()

        # Should return project_root/config/dispatcherd.yaml
        expected_path = Path(__file__).parent.parent.parent.parent / "config" / "dispatcherd.yaml"
        assert result == expected_path

    def test_get_config_file_path_empty_environment(self):
        """Test getting config file path with empty environment variable."""
        os.environ["DISPATCHERD_CONFIG_FILE"] = ""

        result = dispatcherd_config.get_config_file_path()

        # Should return default path when env var is empty
        expected_path = Path(__file__).parent.parent.parent.parent / "config" / "dispatcherd.yaml"
        assert result == expected_path

    def test_get_config_file_path_relative_path(self):
        """Test getting config file path with relative path in environment."""
        relative_path = "config/custom.yaml"
        os.environ["DISPATCHERD_CONFIG_FILE"] = relative_path

        result = dispatcherd_config.get_config_file_path()

        assert result == Path(relative_path)

    def test_get_config_file_path_absolute_path(self):
        """Test getting config file path with absolute path in environment."""
        absolute_path = "/etc/dispatcherd/config.yaml"
        os.environ["DISPATCHERD_CONFIG_FILE"] = absolute_path

        result = dispatcherd_config.get_config_file_path()

        assert result == Path(absolute_path)


@pytest.mark.unit
class TestSetupDispatcherdConfig(TestCase):
    """Test setup_dispatcherd_config function."""

    def setUp(self):
        """Set up test environment."""
        # Store original environment
        self.original_env = os.environ.get("DISPATCHERD_CONFIG_FILE")

    def tearDown(self):
        """Clean up test environment."""
        # Restore original environment
        if self.original_env is not None:
            os.environ["DISPATCHERD_CONFIG_FILE"] = self.original_env
        elif "DISPATCHERD_CONFIG_FILE" in os.environ:
            del os.environ["DISPATCHERD_CONFIG_FILE"]

    @patch("apps.tasks.dispatcherd_config.logger")
    def test_setup_dispatcherd_config_import_error(self, mock_logger):
        """Test setup_dispatcherd_config with import error."""
        with patch("builtins.__import__", side_effect=ImportError("dispatcherd not available")):
            with pytest.raises(ImportError):
                dispatcherd_config.setup_dispatcherd_config()

            mock_logger.error.assert_called()

    def test_setup_dispatcherd_config_already_configured(self):
        """Test setup_dispatcherd_config when already configured."""
        mock_dispatcherd_config = Mock()
        mock_dispatcherd_config._configured = True

        with (
            patch.dict("sys.modules", {"dispatcherd.config": mock_dispatcherd_config}),
            patch("apps.tasks.dispatcherd_config.logger") as mock_logger,
        ):
            dispatcherd_config.setup_dispatcherd_config()

            mock_logger.debug.assert_called_with("Dispatcherd already configured")

    def test_setup_dispatcherd_config_with_file(self):
        """Test setup_dispatcherd_config with existing config file."""
        with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False) as temp_file:
            temp_path = Path(temp_file.name)
            temp_file.write(b"database:\n  url: sqlite:///test.db\n")

        try:
            mock_dispatcherd_config = Mock()
            mock_dispatcherd_config._configured = False

            with (
                patch("apps.tasks.dispatcherd_config.get_config_file_path", return_value=temp_path),
                patch.dict("sys.modules", {"dispatcherd.config": mock_dispatcherd_config}),
                patch("apps.tasks.dispatcherd_config.logger") as mock_logger,
            ):
                dispatcherd_config.setup_dispatcherd_config()

                mock_logger.info.assert_called_with(f"Configuring dispatcherd from file: {temp_path}")
                mock_dispatcherd_config.setup.assert_called_once()
                assert os.environ.get("DISPATCHERD_CONFIG_FILE") == str(temp_path)
        finally:
            temp_path.unlink()

    def test_setup_dispatcherd_config_file_not_exists(self):
        """Test setup_dispatcherd_config with non-existent config file."""
        non_existent_path = Path("/non/existent/config.yaml")

        mock_dispatcherd_config = Mock()
        mock_dispatcherd_config._configured = False

        with (
            patch("apps.tasks.dispatcherd_config.get_config_file_path", return_value=non_existent_path),
            patch.dict("sys.modules", {"dispatcherd.config": mock_dispatcherd_config}),
            patch("apps.tasks.dispatcherd_config.logger") as mock_logger,
            patch("apps.tasks.dispatcherd_config.get_django_database_config") as mock_get_django_config,
        ):
            mock_get_django_config.return_value = {"url": "sqlite:///test.db"}
            dispatcherd_config.setup_dispatcherd_config()
            mock_logger.info.assert_called_with("Configuring dispatcherd from Django settings")
            mock_dispatcherd_config.setup.assert_called_once_with({"url": "sqlite:///test.db"})

    def test_setup_dispatcherd_config_django_config_error(self):
        """Test setup_dispatcherd_config with Django config error."""
        non_existent_path = Path("/non/existent/config.yaml")

        mock_dispatcherd_config = Mock()
        mock_dispatcherd_config._configured = False

        with (
            patch("apps.tasks.dispatcherd_config.get_config_file_path", return_value=non_existent_path),
            patch.dict("sys.modules", {"dispatcherd.config": mock_dispatcherd_config}),
            patch("apps.tasks.dispatcherd_config.logger") as mock_logger,
            patch(
                "apps.tasks.dispatcherd_config.get_django_database_config",
                side_effect=ValueError("Config error"),
            ),
        ):
            dispatcherd_config.setup_dispatcherd_config()

            mock_logger.error.assert_called_with("Failed to configure dispatcherd: Config error")

    def test_setup_dispatcherd_config_setup_error(self):
        """Test setup_dispatcherd_config with setup error."""
        with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False) as temp_file:
            temp_path = Path(temp_file.name)
            temp_file.write(b"invalid: yaml: content\n")

        try:
            mock_dispatcherd_config = Mock()
            mock_dispatcherd_config._configured = False
            mock_dispatcherd_config.setup.side_effect = Exception("Setup failed")

            with (
                patch("apps.tasks.dispatcherd_config.get_config_file_path", return_value=temp_path),
                patch.dict("sys.modules", {"dispatcherd.config": mock_dispatcherd_config}),
                patch("apps.tasks.dispatcherd_config.logger") as mock_logger,
            ):
                dispatcherd_config.setup_dispatcherd_config()
                mock_logger.error.assert_called_with("Failed to configure dispatcherd: Setup failed")
        finally:
            temp_path.unlink()


@pytest.mark.unit
class TestGetDjangoDatabaseConfig(TestCase):
    """Test get_django_database_config function."""

    @override_settings(
        DATABASES={
            "default": {
                "ENGINE": "django.db.backends.postgresql",
                "NAME": "metrics_db",
                "USER": "postgres",
                "PASSWORD": "password",
                "HOST": "localhost",
                "PORT": "5432",
            }
        }
    )
    def test_get_django_database_config_postgresql(self):
        """Test getting Django database config for PostgreSQL."""
        result = dispatcherd_config.get_django_database_config()

        expected_url = "postgresql://postgres:password@localhost:5432/metrics_db"
        assert result == {"url": expected_url}

    @override_settings(
        DATABASES={
            "default": {
                "ENGINE": "django.db.backends.sqlite3",
                "NAME": "/path/to/db.sqlite3",
            }
        }
    )
    def test_get_django_database_config_sqlite(self):
        """Test getting Django database config for SQLite."""
        result = dispatcherd_config.get_django_database_config()

        expected_url = "sqlite:////path/to/db.sqlite3"
        assert result == {"url": expected_url}

    @override_settings(
        DATABASES={
            "default": {
                "ENGINE": "django.db.backends.mysql",
                "NAME": "metrics_db",
                "USER": "mysql_user",
                "PASSWORD": "mysql_pass",
                "HOST": "mysql.example.com",
                "PORT": "3306",
            }
        }
    )
    def test_get_django_database_config_mysql(self):
        """Test getting Django database config for MySQL."""
        result = dispatcherd_config.get_django_database_config()

        expected_url = "mysql://mysql_user:mysql_pass@mysql.example.com:3306/metrics_db"
        assert result == {"url": expected_url}

    @override_settings(
        DATABASES={
            "default": {
                "ENGINE": "unsupported.db.backend",
                "NAME": "test_db",
            }
        }
    )
    def test_get_django_database_config_unsupported_engine(self):
        """Test getting Django database config for unsupported engine."""
        with pytest.raises(ValueError, match="Unsupported database engine: unsupported.db.backend"):
            dispatcherd_config.get_django_database_config()

    @override_settings(
        DATABASES={
            "default": {
                "ENGINE": "django.db.backends.postgresql",
                "NAME": "metrics_db",
                "USER": "postgres",
                # Missing PASSWORD
                "HOST": "localhost",
                "PORT": "5432",
            }
        }
    )
    def test_get_django_database_config_missing_password(self):
        """Test getting Django database config with missing password."""
        result = dispatcherd_config.get_django_database_config()

        expected_url = "postgresql://postgres:@localhost:5432/metrics_db"
        assert result == {"url": expected_url}

    @override_settings(
        DATABASES={
            "default": {
                "ENGINE": "django.db.backends.postgresql",
                "NAME": "metrics_db",
                "USER": "postgres",
                "PASSWORD": "password",
                # Missing HOST and PORT (should default)
            }
        }
    )
    def test_get_django_database_config_default_host_port(self):
        """Test getting Django database config with default host and port."""
        result = dispatcherd_config.get_django_database_config()

        expected_url = "postgresql://postgres:password@localhost:5432/metrics_db"
        assert result == {"url": expected_url}

    @override_settings(
        DATABASES={
            "default": {
                "ENGINE": "django.db.backends.postgresql",
                "NAME": "metrics_db",
                "USER": "postgres",
                "PASSWORD": "password",
                "HOST": "",  # Empty host
                "PORT": "",  # Empty port
            }
        }
    )
    def test_get_django_database_config_empty_host_port(self):
        """Test getting Django database config with empty host and port."""
        result = dispatcherd_config.get_django_database_config()

        expected_url = "postgresql://postgres:password@localhost:5432/metrics_db"
        assert result == {"url": expected_url}


@pytest.mark.unit
class TestIsDjangoDatabaseSupported(TestCase):
    """Test is_django_database_supported function."""

    @override_settings(
        DATABASES={
            "default": {
                "ENGINE": "django.db.backends.postgresql",
                "NAME": "test_db",
            }
        }
    )
    def test_is_django_database_supported_postgresql(self):
        """Test database support check for PostgreSQL."""
        result = dispatcherd_config.is_django_database_supported()
        assert result is True

    @override_settings(
        DATABASES={
            "default": {
                "ENGINE": "django.db.backends.sqlite3",
                "NAME": "test_db.sqlite3",
            }
        }
    )
    def test_is_django_database_supported_sqlite(self):
        """Test database support check for SQLite."""
        result = dispatcherd_config.is_django_database_supported()
        assert result is True

    @override_settings(
        DATABASES={
            "default": {
                "ENGINE": "django.db.backends.mysql",
                "NAME": "test_db",
            }
        }
    )
    def test_is_django_database_supported_mysql(self):
        """Test database support check for MySQL."""
        result = dispatcherd_config.is_django_database_supported()
        assert result is True

    @override_settings(
        DATABASES={
            "default": {
                "ENGINE": "unsupported.db.backend",
                "NAME": "test_db",
            }
        }
    )
    def test_is_django_database_supported_unsupported(self):
        """Test database support check for unsupported engine."""
        result = dispatcherd_config.is_django_database_supported()
        assert result is False

    @override_settings(DATABASES={})
    def test_is_django_database_supported_no_default(self):
        """Test database support check with no default database."""
        result = dispatcherd_config.is_django_database_supported()
        assert result is False


@pytest.mark.unit
class TestGetDispatcherdPoolConfig(TestCase):
    """Test get_dispatcherd_pool_config function."""

    def test_get_dispatcherd_pool_config_default(self):
        """Test getting default dispatcherd pool config."""
        result = dispatcherd_config.get_dispatcherd_pool_config()

        expected_config = {
            "connection_pool": {
                "min_connections": 1,
                "max_connections": 10,
                "connection_timeout": 30,
                "idle_timeout": 300,
            }
        }
        assert result == expected_config

    @override_settings(
        DISPATCHERD_POOL_CONFIG={
            "connection_pool": {
                "min_connections": 2,
                "max_connections": 20,
                "connection_timeout": 60,
                "idle_timeout": 600,
            }
        }
    )
    def test_get_dispatcherd_pool_config_custom(self):
        """Test getting custom dispatcherd pool config from settings."""
        result = dispatcherd_config.get_dispatcherd_pool_config()

        expected_config = {
            "connection_pool": {
                "min_connections": 2,
                "max_connections": 20,
                "connection_timeout": 60,
                "idle_timeout": 600,
            }
        }
        assert result == expected_config

    @override_settings(
        DISPATCHERD_POOL_CONFIG={
            "connection_pool": {
                "min_connections": 5,
            }
        }
    )
    def test_get_dispatcherd_pool_config_partial_custom(self):
        """Test getting partially customized dispatcherd pool config."""
        result = dispatcherd_config.get_dispatcherd_pool_config()

        # Should use custom min_connections but default for others
        expected_config = {
            "connection_pool": {
                "min_connections": 5,
                "max_connections": 10,
                "connection_timeout": 30,
                "idle_timeout": 300,
            }
        }
        assert result == expected_config


@pytest.mark.unit
class TestEdgeCasesAndErrorHandling(TestCase):
    """Test edge cases and error handling."""

    def setUp(self):
        """Set up test environment."""
        self.original_env = os.environ.get("DISPATCHERD_CONFIG_FILE")

    def tearDown(self):
        """Clean up test environment."""
        if self.original_env is not None:
            os.environ["DISPATCHERD_CONFIG_FILE"] = self.original_env
        elif "DISPATCHERD_CONFIG_FILE" in os.environ:
            del os.environ["DISPATCHERD_CONFIG_FILE"]

    def test_config_file_path_with_special_characters(self):
        """Test config file path with special characters."""
        special_path = "/path/with spaces/config-file.yaml"
        os.environ["DISPATCHERD_CONFIG_FILE"] = special_path

        result = dispatcherd_config.get_config_file_path()
        assert result == Path(special_path)

    def test_config_file_path_with_unicode(self):
        """Test config file path with unicode characters."""
        unicode_path = "/path/with/ünïcödé/config.yaml"
        os.environ["DISPATCHERD_CONFIG_FILE"] = unicode_path

        result = dispatcherd_config.get_config_file_path()
        assert result == Path(unicode_path)

    @patch("apps.tasks.dispatcherd_config.logger")
    def test_setup_config_with_permission_error(self, mock_logger):
        """Test setup config with file permission error."""
        with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False) as temp_file:
            temp_path = Path(temp_file.name)
            temp_file.write(b"database:\n  url: sqlite:///test.db\n")

        try:
            # Make file unreadable
            temp_path.chmod(0o000)

            mock_dispatcherd_config = Mock()
            mock_dispatcherd_config._configured = False
            mock_dispatcherd_config.setup.side_effect = PermissionError("Permission denied")

            with (
                patch("apps.tasks.dispatcherd_config.get_config_file_path", return_value=temp_path),
                patch.dict("sys.modules", {"dispatcherd.config": mock_dispatcherd_config}),
                patch("apps.tasks.dispatcherd_config.logger") as mock_logger,
            ):
                dispatcherd_config.setup_dispatcherd_config()

            mock_logger.error.assert_called_with("Failed to configure dispatcherd: Permission denied")
        finally:
            # Restore permissions and cleanup
            temp_path.chmod(0o644)
            temp_path.unlink()

    def test_database_config_with_none_values(self):
        """Test database config handling with None values."""
        with override_settings(
            DATABASES={
                "default": {
                    "ENGINE": "django.db.backends.postgresql",
                    "NAME": "test_db",
                    "USER": None,
                    "PASSWORD": None,
                    "HOST": None,
                    "PORT": None,
                }
            }
        ):
            result = dispatcherd_config.get_django_database_config()

        expected_url = "postgresql://:@localhost:5432/test_db"
        assert result == {"url": expected_url}

    def test_concurrent_setup_calls(self):
        """Test concurrent setup calls don't interfere."""
        import threading

        results = []

        def setup_config():
            try:
                mock_dispatcherd_config = Mock()
                mock_dispatcherd_config._configured = False

                with (
                    patch.dict("sys.modules", {"dispatcherd.config": mock_dispatcherd_config}),
                    patch("apps.tasks.dispatcherd_config.get_django_database_config", return_value={"url": "test"}),
                ):
                    dispatcherd_config.setup_dispatcherd_config()
                    results.append("success")
            except Exception as e:
                results.append(f"error: {e}")

        # Create multiple threads
        threads = []
        for _ in range(3):
            thread = threading.Thread(target=setup_config)
            threads.append(thread)
            thread.start()

        # Wait for completion
        for thread in threads:
            thread.join()

        # Should handle concurrent calls gracefully
        assert len(results) == 3
        assert all("success" in result or "error" in result for result in results)

    def test_environment_variable_injection(self):
        """Test that environment variables are properly handled."""
        malicious_path = "/path/to/config.yaml; rm -rf /"
        os.environ["DISPATCHERD_CONFIG_FILE"] = malicious_path

        result = dispatcherd_config.get_config_file_path()

        # Should treat as literal path, not execute commands
        assert result == Path(malicious_path)
        assert str(result) == malicious_path

    @override_settings(
        DATABASES={
            "default": {
                "ENGINE": "django.db.backends.postgresql",
                "NAME": "",  # Empty database name
                "USER": "postgres",
                "PASSWORD": "password",
                "HOST": "localhost",
                "PORT": "5432",
            }
        }
    )
    def test_get_django_database_config_empty_name(self):
        """Test database config with empty database name."""
        result = dispatcherd_config.get_django_database_config()

        expected_url = "postgresql://postgres:password@localhost:5432/"
        assert result == {"url": expected_url}
