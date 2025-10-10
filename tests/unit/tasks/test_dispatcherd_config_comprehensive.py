"""
Comprehensive unit tests for dispatcherd config.
"""

import os
from pathlib import Path
from unittest.mock import Mock, patch

from django.test import TestCase

from apps.tasks import dispatcherd_config


class DispatcherdConfigTestCase(TestCase):
    """Test cases for dispatcherd configuration functions."""

    def setUp(self):
        """Set up test data."""
        # Store original environment
        self.original_env = os.environ.get("DISPATCHERD_CONFIG_FILE")

    def tearDown(self):
        """Clean up after tests."""
        # Restore original environment
        if self.original_env is not None:
            os.environ["DISPATCHERD_CONFIG_FILE"] = self.original_env
        elif "DISPATCHERD_CONFIG_FILE" in os.environ:
            del os.environ["DISPATCHERD_CONFIG_FILE"]

    def test_get_config_file_path_from_env(self):
        """Test getting config file path from environment variable."""
        test_path = "/custom/path/dispatcherd.yaml"
        os.environ["DISPATCHERD_CONFIG_FILE"] = test_path

        result = dispatcherd_config.get_config_file_path()

        self.assertEqual(result, Path(test_path))

    def test_get_config_file_path_default(self):
        """Test getting default config file path."""
        # Remove environment variable if set
        if "DISPATCHERD_CONFIG_FILE" in os.environ:
            del os.environ["DISPATCHERD_CONFIG_FILE"]

        result = dispatcherd_config.get_config_file_path()

        expected_path = Path(__file__).parent.parent.parent.parent / "config" / "dispatcherd.yaml"
        self.assertEqual(result, expected_path)

    @patch("apps.tasks.dispatcherd_config.get_config_file_path")
    def test_setup_dispatcherd_config_with_file(self, mock_get_path):
        """Test setup dispatcherd config with configuration file."""
        mock_config_file = Mock()
        mock_config_file.exists.return_value = True
        mock_config_file.__str__ = lambda x: "/test/config.yaml"
        mock_get_path.return_value = mock_config_file

        mock_dispatcherd_config = Mock()
        mock_dispatcherd_config._configured = False

        with patch.dict("sys.modules", {"dispatcherd.config": mock_dispatcherd_config}):
            dispatcherd_config.setup_dispatcherd_config()

            mock_dispatcherd_config.setup.assert_called_once()
            self.assertEqual(os.environ.get("DISPATCHERD_CONFIG_FILE"), "/test/config.yaml")

    @patch("apps.tasks.dispatcherd_config.get_config_file_path")
    def test_setup_dispatcherd_config_already_configured(self, mock_get_path):
        """Test setup dispatcherd config when already configured."""
        mock_config_file = Mock()
        mock_config_file.exists.return_value = True
        mock_get_path.return_value = mock_config_file

        mock_dispatcherd_config = Mock()
        mock_dispatcherd_config._configured = True

        with patch.dict("sys.modules", {"dispatcherd.config": mock_dispatcherd_config}):
            dispatcherd_config.setup_dispatcherd_config()

            mock_dispatcherd_config.setup.assert_not_called()

    @patch("apps.tasks.dispatcherd_config.get_config_file_path")
    @patch("apps.tasks.dispatcherd_config.get_django_db_config")
    def test_setup_dispatcherd_config_no_file(self, mock_get_db_config, mock_get_path):
        """Test setup dispatcherd config without configuration file."""
        mock_config_file = Mock()
        mock_config_file.exists.return_value = False
        mock_get_path.return_value = mock_config_file

        mock_db_config = {"database": {"url": "sqlite:///test.db"}}
        mock_get_db_config.return_value = mock_db_config

        mock_dispatcherd_config = Mock()
        mock_dispatcherd_config._configured = False

        with patch.dict("sys.modules", {"dispatcherd.config": mock_dispatcherd_config}):
            dispatcherd_config.setup_dispatcherd_config()

            mock_dispatcherd_config.configure.assert_called_once_with(mock_db_config)

    @patch("apps.tasks.dispatcherd_config.get_config_file_path")
    def test_setup_dispatcherd_config_import_error(self, mock_get_path):
        """Test setup dispatcherd config with import error."""
        mock_config_file = Mock()
        mock_config_file.exists.return_value = True
        mock_get_path.return_value = mock_config_file

        # Should not raise exception
        dispatcherd_config.setup_dispatcherd_config()

    def test_get_django_db_config_sqlite(self):
        """Test getting Django database config for SQLite."""
        mock_db_config = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": "/path/to/db.sqlite3"}}

        with patch("django.conf.settings.DATABASES", mock_db_config):
            result = dispatcherd_config.get_django_db_config()

            expected = {"database": {"url": "sqlite:////path/to/db.sqlite3"}}
            self.assertEqual(result, expected)

    def test_get_django_db_config_postgresql(self):
        """Test getting Django database config for PostgreSQL."""
        mock_db_config = {
            "default": {
                "ENGINE": "django.db.backends.postgresql",
                "NAME": "test_db",
                "USER": "test_user",
                "PASSWORD": "test_pass",
                "HOST": "localhost",
                "PORT": "5432",
            }
        }

        with patch("django.conf.settings.DATABASES", mock_db_config):
            result = dispatcherd_config.get_django_db_config()

            expected = {"database": {"url": "postgresql://test_user:test_pass@localhost:5432/test_db"}}
            self.assertEqual(result, expected)

    def test_get_django_db_config_mysql(self):
        """Test getting Django database config for MySQL."""
        mock_db_config = {
            "default": {
                "ENGINE": "django.db.backends.mysql",
                "NAME": "test_db",
                "USER": "test_user",
                "PASSWORD": "test_pass",
                "HOST": "localhost",
                "PORT": "3306",
            }
        }

        with patch("django.conf.settings.DATABASES", mock_db_config):
            result = dispatcherd_config.get_django_db_config()

            expected = {"database": {"url": "mysql://test_user:test_pass@localhost:3306/test_db"}}
            self.assertEqual(result, expected)

    def test_get_django_db_config_unsupported_engine(self):
        """Test getting Django database config for unsupported engine."""
        mock_db_config = {"default": {"ENGINE": "django.db.backends.oracle", "NAME": "test_db"}}

        with patch("django.conf.settings.DATABASES", mock_db_config):
            with self.assertRaises(ValueError) as cm:
                dispatcherd_config.get_django_db_config()

            self.assertIn("Unsupported database engine", str(cm.exception))

    def test_get_django_db_config_missing_default(self):
        """Test getting Django database config with missing default."""
        mock_db_config = {"other": {"ENGINE": "django.db.backends.sqlite3", "NAME": "/path/to/db.sqlite3"}}

        with patch("django.conf.settings.DATABASES", mock_db_config):
            with self.assertRaises(ValueError) as cm:
                dispatcherd_config.get_django_db_config()

            self.assertIn("Default database configuration not found", str(cm.exception))

    def test_build_database_url_postgresql_no_port(self):
        """Test building PostgreSQL URL without port."""
        db_config = {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": "test_db",
            "USER": "test_user",
            "PASSWORD": "test_pass",
            "HOST": "localhost",
        }

        result = dispatcherd_config.build_database_url(db_config)

        expected = "postgresql://test_user:test_pass@localhost/test_db"
        self.assertEqual(result, expected)

    def test_build_database_url_postgresql_no_password(self):
        """Test building PostgreSQL URL without password."""
        db_config = {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": "test_db",
            "USER": "test_user",
            "HOST": "localhost",
            "PORT": "5432",
        }

        result = dispatcherd_config.build_database_url(db_config)

        expected = "postgresql://test_user@localhost:5432/test_db"
        self.assertEqual(result, expected)

    def test_build_database_url_mysql_full(self):
        """Test building MySQL URL with all parameters."""
        db_config = {
            "ENGINE": "django.db.backends.mysql",
            "NAME": "test_db",
            "USER": "test_user",
            "PASSWORD": "test_pass",
            "HOST": "localhost",
            "PORT": "3306",
        }

        result = dispatcherd_config.build_database_url(db_config)

        expected = "mysql://test_user:test_pass@localhost:3306/test_db"
        self.assertEqual(result, expected)

    def test_build_database_url_sqlite_absolute_path(self):
        """Test building SQLite URL with absolute path."""
        db_config = {"ENGINE": "django.db.backends.sqlite3", "NAME": "/absolute/path/to/db.sqlite3"}

        result = dispatcherd_config.build_database_url(db_config)

        expected = "sqlite:////absolute/path/to/db.sqlite3"
        self.assertEqual(result, expected)

    def test_build_database_url_sqlite_relative_path(self):
        """Test building SQLite URL with relative path."""
        db_config = {"ENGINE": "django.db.backends.sqlite3", "NAME": "relative/path/db.sqlite3"}

        result = dispatcherd_config.build_database_url(db_config)

        expected = "sqlite:///relative/path/db.sqlite3"
        self.assertEqual(result, expected)

    def test_validate_dispatcherd_setup_success(self):
        """Test validating dispatcherd setup successfully."""
        mock_dispatcherd_config = Mock()
        mock_dispatcherd_config._configured = True

        with patch.dict("sys.modules", {"dispatcherd.config": mock_dispatcherd_config}):
            result = dispatcherd_config.validate_dispatcherd_setup()

            self.assertTrue(result)

    def test_validate_dispatcherd_setup_not_configured(self):
        """Test validating dispatcherd setup when not configured."""
        mock_dispatcherd_config = Mock()
        mock_dispatcherd_config._configured = False

        with patch.dict("sys.modules", {"dispatcherd.config": mock_dispatcherd_config}):
            result = dispatcherd_config.validate_dispatcherd_setup()

            self.assertFalse(result)

    def test_validate_dispatcherd_setup_import_error(self):
        """Test validating dispatcherd setup with import error."""
        result = dispatcherd_config.validate_dispatcherd_setup()

        self.assertFalse(result)

    def test_module_imports(self):
        """Test that all required imports work."""
        from apps.tasks import dispatcherd_config

        # Test that key functions are available
        self.assertTrue(hasattr(dispatcherd_config, "get_config_file_path"))
        self.assertTrue(hasattr(dispatcherd_config, "setup_dispatcherd_config"))
        self.assertTrue(hasattr(dispatcherd_config, "get_django_db_config"))
        self.assertTrue(hasattr(dispatcherd_config, "build_database_url"))
        self.assertTrue(hasattr(dispatcherd_config, "validate_dispatcherd_setup"))

    def test_logger_configured(self):
        """Test that logger is properly configured."""
        from apps.tasks import dispatcherd_config

        self.assertTrue(hasattr(dispatcherd_config, "logger"))
        self.assertEqual(dispatcherd_config.logger.name, "apps.tasks.dispatcherd_config")

    def test_path_imports(self):
        """Test that Path and other imports are available."""
        from apps.tasks import dispatcherd_config

        # Test that required imports are available
        self.assertTrue(hasattr(dispatcherd_config, "Path"))
        self.assertTrue(hasattr(dispatcherd_config, "os"))
        self.assertTrue(hasattr(dispatcherd_config, "logging"))
