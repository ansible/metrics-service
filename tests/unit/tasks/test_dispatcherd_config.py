"""
Comprehensive unit tests for apps.tasks.dispatcherd_config module.

This module tests all functions in the dispatcherd_config module to achieve
full code coverage.
"""

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from apps.tasks.dispatcherd_config import (
    _load_config_with_django_db,
    build_config_from_django_settings,
    ensure_dispatcherd_configured,
    get_config_file_path,
    setup_dispatcherd_config,
)


class TestGetConfigFilePath:
    """Tests for get_config_file_path function."""

    def test_returns_path_from_environment_variable(self):
        """Test that the function returns path from DISPATCHERD_CONFIG_FILE env var."""
        test_path = "/custom/path/to/dispatcherd.yaml"
        with patch.dict(os.environ, {"DISPATCHERD_CONFIG_FILE": test_path}):
            result = get_config_file_path()
            assert result == Path(test_path)

    def test_returns_default_path_when_no_env_var(self):
        """Test that the function returns default path when env var is not set."""
        with patch.dict(os.environ, {}, clear=True):
            result = get_config_file_path()
            # Should return apps/settings/dispatcherd.yaml relative to project root
            assert result.name == "dispatcherd.yaml"
            assert result.parent.name == "settings"
            assert result.parent.parent.name == "apps"

    def test_returns_path_object(self):
        """Test that the function returns a Path object."""
        result = get_config_file_path()
        assert isinstance(result, Path)


class TestSetupDispatcherdConfig:
    """Tests for setup_dispatcherd_config function."""

    @patch("apps.tasks.dispatcherd_config.get_config_file_path")
    @patch("apps.tasks.dispatcherd_config.logger")
    def test_skips_if_already_configured(self, mock_logger, mock_get_path):
        """Test that setup skips if dispatcherd is already configured."""
        mock_config = MagicMock()
        mock_config._configured = True

        # Must mock hasattr to return True
        with (
            patch.dict("sys.modules", {"dispatcherd": MagicMock(), "dispatcherd.config": mock_config}),
            patch("builtins.hasattr", return_value=True),
        ):
            setup_dispatcherd_config()

        mock_logger.debug.assert_called_with("Dispatcherd already configured")
        mock_get_path.assert_not_called()

    @patch("apps.tasks.dispatcherd_config.logger")
    def test_raises_on_import_error(self, mock_logger):
        """Test that setup raises ImportError when dispatcherd is not available."""
        with patch.dict("sys.modules", {"dispatcherd.config": None}), pytest.raises(ImportError):
            setup_dispatcherd_config()

        mock_logger.error.assert_called()
        assert "Failed to import dispatcherd" in str(mock_logger.error.call_args)

    # Note: Tests for specific setup behaviors (using config file, using Django settings,
    # error handling) are difficult to implement due to the _configured check in
    # setup_dispatcherd_config interacting poorly with MagicMock's hasattr behavior.
    # The function is adequately tested through integration tests and the individual
    # helper functions (get_config_file_path, build_config_from_django_settings) are
    # thoroughly tested below.

    @patch("apps.tasks.dispatcherd_config._load_config_with_django_db")
    @patch("apps.tasks.dispatcherd_config.get_config_file_path")
    @patch("apps.tasks.dispatcherd_config.logger")
    def test_loads_config_from_file_when_exists(self, mock_logger, mock_get_path, mock_load_config):
        """Test that setup loads config from file when file exists."""
        mock_config_file = MagicMock()
        mock_config_file.exists.return_value = True
        mock_get_path.return_value = mock_config_file

        mock_config = {"test": "config"}
        mock_load_config.return_value = mock_config

        mock_dispatcherd = MagicMock()
        mock_dispatcherd.config._configured = False

        with (
            patch.dict("sys.modules", {"dispatcherd": mock_dispatcherd, "dispatcherd.config": mock_dispatcherd.config}),
            patch("builtins.hasattr", return_value=False),
        ):
            setup_dispatcherd_config()

        mock_load_config.assert_called_once_with(mock_config_file)
        mock_dispatcherd.config.setup.assert_called_once_with(mock_config)
        assert mock_dispatcherd.config._configured is True

    @patch("apps.tasks.dispatcherd_config.build_config_from_django_settings")
    @patch("apps.tasks.dispatcherd_config.get_config_file_path")
    @patch("apps.tasks.dispatcherd_config.logger")
    def test_builds_config_from_django_when_file_missing(self, mock_logger, mock_get_path, mock_build_config):
        """Test that setup builds config from Django settings when file doesn't exist."""
        mock_config_file = MagicMock()
        mock_config_file.exists.return_value = False
        mock_get_path.return_value = mock_config_file

        mock_config = {"test": "config"}
        mock_build_config.return_value = mock_config

        mock_dispatcherd = MagicMock()
        mock_dispatcherd.config._configured = False

        with (
            patch.dict("sys.modules", {"dispatcherd": mock_dispatcherd, "dispatcherd.config": mock_dispatcherd.config}),
            patch("builtins.hasattr", return_value=False),
        ):
            setup_dispatcherd_config()

        mock_build_config.assert_called_once()
        mock_dispatcherd.config.setup.assert_called_once_with(mock_config)
        assert mock_dispatcherd.config._configured is True

    @patch("apps.tasks.dispatcherd_config.get_config_file_path")
    @patch("apps.tasks.dispatcherd_config.logger")
    def test_raises_and_logs_on_general_exception(self, mock_logger, mock_get_path):
        """Test that setup raises and logs general exceptions."""
        mock_get_path.side_effect = Exception("Configuration error")

        mock_dispatcherd = MagicMock()
        mock_dispatcherd.config._configured = False

        with (
            patch.dict("sys.modules", {"dispatcherd": mock_dispatcherd, "dispatcherd.config": mock_dispatcherd.config}),
            patch("builtins.hasattr", return_value=False),
            pytest.raises(Exception, match="Configuration error"),
        ):
            setup_dispatcherd_config()

        mock_logger.exception.assert_called()
        assert "Failed to configure dispatcherd" in str(mock_logger.exception.call_args)


class TestLoadConfigWithDjangoDb:
    """Tests for _load_config_with_django_db function."""

    @patch("django.conf.settings")
    @patch("apps.tasks.dispatcherd_config.logger")
    @patch("builtins.open")
    @patch("yaml.safe_load")
    def test_loads_yaml_and_merges_django_db_config(self, mock_yaml_load, mock_open, mock_logger, mock_settings):
        """Test that function loads YAML config and merges Django database settings."""
        # Arrange
        mock_yaml_config = {
            "version": 2,
            "brokers": {
                "pg_notify": {
                    "config": {
                        "dbname": "old_db",
                        "user": "old_user",
                    },
                    "channels": ["existing_channel"],
                },
            },
        }
        mock_yaml_load.return_value = mock_yaml_config

        mock_settings.DATABASES = {
            "default": {
                "NAME": "new_db",
                "USER": "new_user",
                "PASSWORD": "new_pass",
                "HOST": "new_host",
                "PORT": "5433",
            }
        }

        config_file = Path("/test/config.yaml")

        # Act
        result = _load_config_with_django_db(config_file)

        # Assert
        # Verify YAML was loaded
        mock_open.assert_called_once_with(config_file)
        mock_yaml_load.assert_called_once()

        # Verify database config was overridden with Django settings
        pg_config = result["brokers"]["pg_notify"]["config"]
        assert pg_config["dbname"] == "new_db"
        assert pg_config["user"] == "new_user"
        assert pg_config["password"] == "new_pass"
        assert pg_config["host"] == "new_host"
        assert pg_config["port"] == "5433"

        # Verify logging
        mock_logger.info.assert_called_once()
        assert "new_host:5433/new_db" in str(mock_logger.info.call_args)

    @patch("django.conf.settings")
    @patch("apps.tasks.dispatcherd_config.logger")
    @patch("builtins.open")
    @patch("yaml.safe_load")
    def test_creates_brokers_section_if_missing(self, mock_yaml_load, mock_open, mock_logger, mock_settings):
        """Test that function creates brokers section if not in YAML."""
        # Arrange - YAML with no brokers section
        mock_yaml_config = {"version": 2}
        mock_yaml_load.return_value = mock_yaml_config

        mock_settings.DATABASES = {
            "default": {
                "NAME": "test_db",
                "USER": "test_user",
                "PASSWORD": "test_pass",
                "HOST": "test_host",
                "PORT": "5432",
            }
        }

        config_file = Path("/test/config.yaml")

        # Act
        result = _load_config_with_django_db(config_file)

        # Assert
        assert "brokers" in result
        assert "pg_notify" in result["brokers"]
        assert "config" in result["brokers"]["pg_notify"]

    @patch("django.conf.settings")
    @patch("apps.tasks.dispatcherd_config.logger")
    @patch("builtins.open")
    @patch("yaml.safe_load")
    def test_creates_pg_notify_section_if_missing(self, mock_yaml_load, mock_open, mock_logger, mock_settings):
        """Test that function creates pg_notify section if not in brokers."""
        # Arrange - YAML with brokers but no pg_notify
        mock_yaml_config = {"version": 2, "brokers": {"other_broker": {}}}
        mock_yaml_load.return_value = mock_yaml_config

        mock_settings.DATABASES = {
            "default": {
                "NAME": "test_db",
                "USER": "test_user",
                "PASSWORD": "test_pass",
                "HOST": "test_host",
                "PORT": "5432",
            }
        }

        config_file = Path("/test/config.yaml")

        # Act
        result = _load_config_with_django_db(config_file)

        # Assert
        assert "pg_notify" in result["brokers"]
        assert "config" in result["brokers"]["pg_notify"]

    @patch("django.conf.settings")
    @patch("apps.tasks.dispatcherd_config.logger")
    @patch("builtins.open")
    @patch("yaml.safe_load")
    def test_handles_empty_yaml_file(self, mock_yaml_load, mock_open, mock_logger, mock_settings):
        """Test that function handles empty YAML file (returns None from safe_load)."""
        # Arrange - Empty YAML file
        mock_yaml_load.return_value = None

        mock_settings.DATABASES = {
            "default": {
                "NAME": "test_db",
                "USER": "test_user",
                "PASSWORD": "test_pass",
                "HOST": "test_host",
                "PORT": "5432",
            }
        }

        config_file = Path("/test/config.yaml")

        # Act
        result = _load_config_with_django_db(config_file)

        # Assert
        # Should create default structure
        assert "brokers" in result
        assert "pg_notify" in result["brokers"]
        assert "config" in result["brokers"]["pg_notify"]


class TestBuildConfigFromDjangoSettings:
    """Tests for build_config_from_django_settings function."""

    @patch("django.conf.settings")
    @patch("apps.tasks.dispatcherd_config.logger")
    def test_builds_valid_config(self, mock_logger, mock_settings):
        """Test that function builds valid dispatcherd config from Django settings."""
        mock_settings.DATABASES = {
            "default": {
                "NAME": "test_db",
                "USER": "test_user",
                "PASSWORD": "test_pass",
                "HOST": "localhost",
                "PORT": "5432",
            }
        }

        config = build_config_from_django_settings()

        assert config["version"] == 2
        assert "brokers" in config
        assert "pg_notify" in config["brokers"]
        assert config["brokers"]["pg_notify"]["config"]["dbname"] == "test_db"
        assert config["brokers"]["pg_notify"]["config"]["user"] == "test_user"
        assert config["brokers"]["pg_notify"]["config"]["password"] == "test_pass"  # noqa: S105
        assert config["brokers"]["pg_notify"]["config"]["host"] == "localhost"
        assert config["brokers"]["pg_notify"]["config"]["port"] == "5432"

    @patch("django.conf.settings")
    @patch("apps.tasks.dispatcherd_config.logger")
    def test_includes_all_channels(self, mock_logger, mock_settings):
        """Test that config includes all required channels."""
        mock_settings.DATABASES = {
            "default": {
                "NAME": "test_db",
                "USER": "test_user",
                "PASSWORD": "test_pass",
                "HOST": "localhost",
                "PORT": "5432",
            }
        }

        config = build_config_from_django_settings()

        channels = config["brokers"]["pg_notify"]["channels"]
        assert "dashboard" in channels
        assert "maintenance" in channels
        assert "metrics" in channels

    @patch("django.conf.settings")
    @patch("apps.tasks.dispatcherd_config.logger")
    def test_includes_service_config(self, mock_logger, mock_settings):
        """Test that config includes service configuration."""
        mock_settings.DATABASES = {
            "default": {
                "NAME": "test_db",
                "USER": "test_user",
                "PASSWORD": "test_pass",
                "HOST": "localhost",
                "PORT": "5432",
            }
        }

        config = build_config_from_django_settings()

        assert "service" in config
        assert "pool_kwargs" in config["service"]
        assert config["service"]["pool_kwargs"]["max_workers"] == 4

    @patch("django.conf.settings")
    @patch("apps.tasks.dispatcherd_config.logger")
    def test_logs_database_info(self, mock_logger, mock_settings):
        """Test that function logs database connection info."""
        mock_settings.DATABASES = {
            "default": {
                "NAME": "test_db",
                "USER": "test_user",
                "PASSWORD": "test_pass",
                "HOST": "localhost",
                "PORT": "5432",
            }
        }

        build_config_from_django_settings()

        mock_logger.info.assert_called_once()
        assert "localhost:5432/test_db" in str(mock_logger.info.call_args)

    @patch("django.conf.settings")
    @patch("apps.tasks.dispatcherd_config.logger")
    def test_raises_on_missing_settings(self, mock_logger, mock_settings):
        """Test that function raises exception when Django settings are invalid."""
        mock_settings.DATABASES = {}

        with pytest.raises(KeyError):
            build_config_from_django_settings()

        mock_logger.exception.assert_called()
        assert "Failed to build config from Django settings" in str(mock_logger.exception.call_args)


class TestEnsureDispatcherdConfigured:
    """Tests for ensure_dispatcherd_configured function."""

    @patch("apps.tasks.dispatcherd_config.setup_dispatcherd_config")
    @patch("apps.tasks.dispatcherd_config.logger")
    def test_does_nothing_when_already_configured(self, mock_logger, mock_setup_config):
        """Test that function does nothing if dispatcherd is already configured."""
        mock_config = MagicMock()
        mock_config._configured = True

        with (
            patch.dict("sys.modules", {"dispatcherd": MagicMock(), "dispatcherd.config": mock_config}),
            patch("builtins.hasattr", return_value=True),
        ):
            ensure_dispatcherd_configured()

        mock_setup_config.assert_not_called()

    @patch("apps.tasks.dispatcherd_config.setup_dispatcherd_config")
    @patch("apps.tasks.dispatcherd_config.logger")
    def test_calls_setup_when_not_configured(self, mock_logger, mock_setup_config):
        """Test that function calls setup when dispatcherd is not configured."""
        mock_config = MagicMock()
        mock_config._configured = False

        with (
            patch.dict("sys.modules", {"dispatcherd": MagicMock(), "dispatcherd.config": mock_config}),
            patch("builtins.hasattr", return_value=False),
        ):
            ensure_dispatcherd_configured()

        mock_setup_config.assert_called_once()
        mock_logger.info.assert_called_with("Dispatcherd not configured, setting up configuration...")

    @patch("apps.tasks.dispatcherd_config.logger")
    def test_raises_on_import_error(self, mock_logger):
        """Test that function raises ImportError when dispatcherd is not available."""
        with patch.dict("sys.modules", {"dispatcherd.config": None}), pytest.raises(ImportError):
            ensure_dispatcherd_configured()

        mock_logger.error.assert_called_with("Dispatcherd not available")

    @patch("apps.tasks.dispatcherd_config.setup_dispatcherd_config")
    @patch("apps.tasks.dispatcherd_config.logger")
    def test_raises_and_logs_on_general_exception(self, mock_logger, mock_setup_config):
        """Test that function raises and logs general exceptions from setup."""
        mock_setup_config.side_effect = Exception("Setup failed")

        mock_config = MagicMock()
        mock_config._configured = False

        with (
            patch.dict("sys.modules", {"dispatcherd": MagicMock(), "dispatcherd.config": mock_config}),
            patch("builtins.hasattr", return_value=False),
            pytest.raises(Exception, match="Setup failed"),
        ):
            ensure_dispatcherd_configured()

        mock_logger.exception.assert_called()
        assert "Failed to ensure dispatcherd configuration" in str(mock_logger.exception.call_args)
