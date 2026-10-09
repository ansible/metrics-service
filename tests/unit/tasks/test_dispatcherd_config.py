"""
Comprehensive unit tests for apps.tasks.dispatcherd_config module.

This module tests all functions in the dispatcherd_config module to achieve
full code coverage.
"""

import os
from copy import deepcopy
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from apps.tasks.dispatcherd_config import (
    _load_config_with_dispatcherd_settings,
    build_config_from_settings,
    ensure_dispatcherd_configured,
    get_config_file_path,
    setup_dispatcherd_config,
)


@pytest.mark.parametrize("use_yaml", [False, True])
@pytest.mark.parametrize("password", ["", "test-only"])
def test_dispatcherd_broker_uses_independent_sql_server_settings(use_yaml, password, tmp_path):
    """Broker connection data comes from DISPATCHERD_SQLSERVER, not Django DATABASES."""
    sql_server_config = {
        "server": "sql.example.com",
        "port": 1433,
        "database": "dispatcherd",
        "user": "dispatcherd",
        "password": password,
        "driver": "ODBC Driver 18 for SQL Server",
        "trust_server_certificate": "no",
    }
    database = {"NAME": "metrics_pg", "USER": "pg_user", "PASSWORD": "pg_password", "HOST": "postgres", "PORT": "5432"}
    original_database = deepcopy(database)
    with patch("django.conf.settings") as settings:
        settings.DATABASES = {"default": database}
        settings.DISPATCHERD_SQLSERVER = sql_server_config
        settings.TASK_TIMEOUT = 3600
        if use_yaml:
            config_file = tmp_path / "dispatcherd.yaml"
            config_file.write_text(
                "brokers:\n  sql_server:\n    config:\n      server: old-server\n    channels: [existing]\n"
            )
            config = _load_config_with_dispatcherd_settings(config_file)
            assert config["brokers"]["sql_server"]["channels"] == ["existing"]
        else:
            config = build_config_from_settings()

    assert config["brokers"]["sql_server"]["config"] == sql_server_config
    assert database == original_database
    assert settings.DATABASES["default"] == original_database


def test_build_config_normalizes_dynaconf_uppercase_sql_server_overrides():
    with patch("django.conf.settings") as settings:
        settings.DISPATCHERD_SQLSERVER = {
            "server": "",
            "port": 1433,
            "database": "dispatcherd",
            "user": "",
            "password": "",
            "driver": "ODBC Driver 18 for SQL Server",
            "trust_server_certificate": "yes",
            "SERVER": "sql.example.com",
            "PORT": "1444",
            "USER": "broker_user",
            "PASSWORD": "env-secret",
            "TRUST_SERVER_CERTIFICATE": "no",
        }
        settings.TASK_TIMEOUT = 3600

        config = build_config_from_settings()

    sql_config = config["brokers"]["sql_server"]["config"]
    assert sql_config["server"] == "sql.example.com"
    assert sql_config["port"] == "1444"
    assert sql_config["user"] == "broker_user"
    assert sql_config["password"] == "env-secret"
    assert sql_config["trust_server_certificate"] == "no"
    assert "SERVER" not in sql_config


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
    # helper functions (get_config_file_path, build_config_from_settings) are
    # thoroughly tested below.

    @patch("apps.tasks.dispatcherd_config._load_config_with_dispatcherd_settings")
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

    @patch("apps.tasks.dispatcherd_config.build_config_from_settings")
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


class TestLoadConfigWithDispatcherdSettings:
    """Tests for merging broker settings independently from Django DATABASES."""

    @patch("django.conf.settings")
    @patch("apps.tasks.dispatcherd_config.logger")
    @patch("builtins.open")
    @patch("yaml.safe_load")
    def test_loads_yaml_and_merges_sql_server_config(self, mock_yaml_load, mock_open, mock_logger, mock_settings):
        sql_config = {"server": "sql.example.com", "port": 1433, "database": "dispatcherd", "user": "broker", "password": "secret"}
        mock_yaml_load.return_value = {
            "version": 2,
            "brokers": {
                "pg_notify": {"channels": ["old_pg_channel"]},
                "sql_server": {"config": {"server": "old-server"}, "channels": ["existing_channel"]},
                "other_broker": {},
            },
        }
        mock_settings.DISPATCHERD_SQLSERVER = sql_config
        mock_settings.TASK_TIMEOUT = 2400
        config_file = Path("/test/config.yaml")

        result = _load_config_with_dispatcherd_settings(config_file)

        mock_open.assert_called_once_with(config_file)
        assert result["brokers"]["sql_server"]["config"] == sql_config
        assert result["brokers"]["sql_server"]["channels"] == ["existing_channel"]
        assert "pg_notify" not in result["brokers"]
        assert "other_broker" in result["brokers"]
        assert result["service"]["task_settings"]["default_timeout"] == 2400
        assert "secret" not in str(mock_logger.info.call_args)
        assert "sql.example.com:1433/dispatcherd" in str(mock_logger.info.call_args)

    @patch("django.conf.settings")
    @patch("apps.tasks.dispatcherd_config.logger")
    @patch("builtins.open")
    @patch("yaml.safe_load")
    def test_creates_broker_and_service_sections_if_missing(self, mock_yaml_load, mock_open, mock_logger, mock_settings):
        mock_yaml_load.return_value = {"version": 2}
        mock_settings.DISPATCHERD_SQLSERVER = {"server": "sql", "port": 1433, "database": "dispatcherd", "user": "broker", "password": "secret"}
        mock_settings.TASK_TIMEOUT = 3600

        result = _load_config_with_dispatcherd_settings(Path("/test/config.yaml"))

        assert result["brokers"]["sql_server"]["config"] == mock_settings.DISPATCHERD_SQLSERVER
        assert "pg_notify" not in result["brokers"]
        assert result["service"]["task_settings"]["default_timeout"] == 3600

    @patch("django.conf.settings")
    @patch("apps.tasks.dispatcherd_config.logger")
    @patch("builtins.open")
    @patch("yaml.safe_load")
    def test_handles_empty_yaml_file(self, mock_yaml_load, mock_open, mock_logger, mock_settings):
        mock_yaml_load.return_value = None
        mock_settings.DISPATCHERD_SQLSERVER = {"server": "sql", "port": 1433, "database": "dispatcherd", "user": "broker", "password": "secret"}
        mock_settings.TASK_TIMEOUT = 3600

        result = _load_config_with_dispatcherd_settings(Path("/test/config.yaml"))

        assert result["brokers"]["sql_server"]["config"] == mock_settings.DISPATCHERD_SQLSERVER

    @patch("django.conf.settings")
    @patch("apps.tasks.dispatcherd_config.logger")
    @patch("builtins.open")
    @patch("yaml.safe_load")
    def test_migrates_channels_and_default_publish_channel_from_postgres_broker(
        self, mock_yaml_load, mock_open, mock_logger, mock_settings
    ):
        mock_yaml_load.return_value = {
            "version": 2,
            "brokers": {
                "pg_notify": {
                    "channels": ["metrics", "dashboard"],
                    "default_publish_channel": "metrics",
                }
            },
            "publish": {"default_broker": "pg_notify", "default_control_broker": "pg_notify"},
        }
        mock_settings.DISPATCHERD_SQLSERVER = {"server": "sql.example.com", "database": "dispatcherd"}
        mock_settings.TASK_TIMEOUT = 2400

        result = _load_config_with_dispatcherd_settings(Path("/test/config.yaml"))

        assert result["brokers"]["sql_server"]["channels"] == ["metrics", "dashboard"]
        assert result["brokers"]["sql_server"]["default_publish_channel"] == "metrics"
        assert "pg_notify" not in result["brokers"]
        assert result["publish"] == {"default_broker": "sql_server", "default_control_broker": "sql_server"}


class TestBuildConfigFromSettings:
    """Tests for building a broker config without reading Django DATABASES."""

    @patch("django.conf.settings")
    @patch("apps.tasks.dispatcherd_config.logger")
    def test_builds_sql_server_config_and_keeps_postgres_settings_independent(self, mock_logger, mock_settings):
        sql_config = {"server": "sql.example.com", "port": 1433, "database": "dispatcherd", "user": "broker", "password": "secret"}
        mock_settings.DISPATCHERD_SQLSERVER = sql_config
        mock_settings.DATABASES = {"default": {"HOST": "postgres", "NAME": "metrics_pg"}}
        mock_settings.TASK_TIMEOUT = 3600

        config = build_config_from_settings()

        assert config["version"] == 2
        assert config["brokers"] == {
            "sql_server": {
                "config": sql_config,
                "channels": ["dashboard", "maintenance", "metrics"],
            }
        }
        assert config["service"]["task_settings"]["default_timeout"] == 3600
        assert "secret" not in str(mock_logger.info.call_args)
        assert "sql.example.com:1433/dispatcherd" in str(mock_logger.info.call_args)

    @patch("django.conf.settings")
    @patch("apps.tasks.dispatcherd_config.logger")
    def test_raises_when_dispatcherd_sql_server_setting_is_missing(self, mock_logger, mock_settings):
        mock_settings.DISPATCHERD_SQLSERVER = None

        with pytest.raises(AttributeError):
            build_config_from_settings()

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
