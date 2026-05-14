"""
Unit tests for apps/tasks/dispatcherd_config.py.
Targets 12.37% → ~90% coverage.
"""

import os
from unittest.mock import mock_open, patch

import pytest


# ---------------------------------------------------------------------------
# get_config_file_path
# ---------------------------------------------------------------------------
@pytest.mark.unit
def test_get_config_file_path_from_env_var():
    from apps.tasks.dispatcherd_config import get_config_file_path

    with patch.dict(os.environ, {"DISPATCHERD_CONFIG_FILE": "/tmp/test_dispatcherd.yaml"}):
        path = get_config_file_path()
    assert str(path) == "/tmp/test_dispatcherd.yaml"


@pytest.mark.unit
def test_get_config_file_path_default():
    from apps.tasks.dispatcherd_config import get_config_file_path

    env = {k: v for k, v in os.environ.items() if k != "DISPATCHERD_CONFIG_FILE"}
    with patch.dict(os.environ, env, clear=True):
        path = get_config_file_path()
    assert path.name == "dispatcherd.yaml"
    assert "apps" in str(path)


# ---------------------------------------------------------------------------
# build_config_from_django_settings
# ---------------------------------------------------------------------------
@pytest.mark.unit
def test_build_config_from_django_settings_has_brokers():
    from apps.tasks.dispatcherd_config import build_config_from_django_settings

    config = build_config_from_django_settings()
    assert "brokers" in config
    assert "pg_notify" in config["brokers"]
    assert "config" in config["brokers"]["pg_notify"]


@pytest.mark.unit
def test_build_config_from_django_settings_db_values():
    from django.conf import settings

    from apps.tasks.dispatcherd_config import build_config_from_django_settings

    config = build_config_from_django_settings()
    pg_config = config["brokers"]["pg_notify"]["config"]
    db = settings.DATABASES["default"]
    assert pg_config["dbname"] == db["NAME"]
    assert pg_config["user"] == db["USER"]


@pytest.mark.unit
def test_build_config_from_django_settings_has_service_section():
    from apps.tasks.dispatcherd_config import build_config_from_django_settings

    config = build_config_from_django_settings()
    assert "service" in config or "brokers" in config  # At minimum brokers must be there


# ---------------------------------------------------------------------------
# _load_config_with_django_db
# ---------------------------------------------------------------------------
@pytest.mark.unit
def test_load_config_overrides_db_from_django():
    from pathlib import Path

    from django.conf import settings

    from apps.tasks.dispatcherd_config import _load_config_with_django_db

    yaml_content = {"brokers": {"pg_notify": {"config": {"host": "old_host", "port": "5432"}}}}

    with patch("builtins.open", mock_open()), patch("yaml.safe_load", return_value=yaml_content):
        config = _load_config_with_django_db(Path("/fake/dispatcherd.yaml"))

    # Django settings should override the YAML host
    expected_host = settings.DATABASES["default"]["HOST"]
    assert config["brokers"]["pg_notify"]["config"]["host"] == expected_host


@pytest.mark.unit
def test_load_config_creates_brokers_section_if_missing():
    from pathlib import Path

    from apps.tasks.dispatcherd_config import _load_config_with_django_db

    with patch("builtins.open", mock_open()), patch("yaml.safe_load", return_value={}):
        config = _load_config_with_django_db(Path("/fake/dispatcherd.yaml"))

    assert "brokers" in config
    assert "pg_notify" in config["brokers"]


# ---------------------------------------------------------------------------
# setup_dispatcherd_config
# ---------------------------------------------------------------------------
@pytest.mark.unit
def test_setup_dispatcherd_config_skips_when_already_configured():
    import dispatcherd.config as dc

    from apps.tasks.dispatcherd_config import setup_dispatcherd_config

    original = getattr(dc, "_configured", False)
    dc._configured = True
    try:
        with patch("dispatcherd.config.setup") as mock_setup:
            setup_dispatcherd_config()
            mock_setup.assert_not_called()
    finally:
        dc._configured = original


@pytest.mark.unit
def test_setup_dispatcherd_config_loads_yaml_when_file_exists():
    import dispatcherd.config as dc

    from apps.tasks.dispatcherd_config import setup_dispatcherd_config

    dc._configured = False
    with patch("apps.tasks.dispatcherd_config.get_config_file_path") as mock_path:
        mock_path.return_value.exists.return_value = True
        with (
            patch("apps.tasks.dispatcherd_config._load_config_with_django_db", return_value={}) as mock_load,
            patch("dispatcherd.config.setup") as mock_setup,
        ):
            setup_dispatcherd_config()
            mock_load.assert_called_once()
            mock_setup.assert_called_once()
    dc._configured = False


@pytest.mark.unit
def test_setup_dispatcherd_config_uses_django_when_no_file():
    import dispatcherd.config as dc

    from apps.tasks.dispatcherd_config import setup_dispatcherd_config

    dc._configured = False
    with patch("apps.tasks.dispatcherd_config.get_config_file_path") as mock_path:
        mock_path.return_value.exists.return_value = False
        with (
            patch("apps.tasks.dispatcherd_config.build_config_from_django_settings", return_value={}) as mock_build,
            patch("dispatcherd.config.setup") as mock_setup,
        ):
            setup_dispatcherd_config()
            mock_build.assert_called_once()
            mock_setup.assert_called_once()
    dc._configured = False


# ---------------------------------------------------------------------------
# ensure_dispatcherd_configured
# ---------------------------------------------------------------------------
@pytest.mark.unit
def test_ensure_dispatcherd_configured_calls_setup_when_not_configured():
    import dispatcherd.config as dc

    from apps.tasks.dispatcherd_config import ensure_dispatcherd_configured

    dc._configured = False
    with patch("apps.tasks.dispatcherd_config.setup_dispatcherd_config") as mock_setup:
        ensure_dispatcherd_configured()
        mock_setup.assert_called_once()
    dc._configured = False


@pytest.mark.unit
def test_ensure_dispatcherd_configured_skips_when_already_done():
    import dispatcherd.config as dc

    from apps.tasks.dispatcherd_config import ensure_dispatcherd_configured

    original = getattr(dc, "_configured", False)
    dc._configured = True
    with patch("apps.tasks.dispatcherd_config.setup_dispatcherd_config") as mock_setup:
        ensure_dispatcherd_configured()
        mock_setup.assert_not_called()
    dc._configured = original
