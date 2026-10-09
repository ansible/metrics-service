"""
Dispatcherd configuration utilities for metrics service.

This module provides utilities for configuring dispatcherd across different
processes and components of the metrics service.
"""

import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)
DEFAULT_CHANNELS = ["dashboard", "maintenance", "metrics"]


def get_config_file_path() -> Path:
    """Get the path to the dispatcherd configuration file."""
    # Check if environment variable is set
    config_file = os.environ.get("DISPATCHERD_CONFIG_FILE")
    if config_file:
        return Path(config_file)

    # Default to apps/settings/dispatcherd.yaml in project root
    project_root = Path(__file__).parent.parent.parent
    return project_root / "apps" / "settings" / "dispatcherd.yaml"


def setup_dispatcherd_config() -> None:
    """
    Setup dispatcherd configuration from file or Django settings.

    This function configures dispatcherd to work with the metrics service
    SQL Server broker and task queues. It can be called from any process that needs
    to submit tasks to dispatcherd.

    Broker connection settings come from DISPATCHERD_SQLSERVER and remain
    independent from Django's DATABASES setting. The YAML config file provides
    channels, queue routing, logging, and worker pool settings.
    """
    try:
        import dispatcherd.config

        # Check if already configured
        if hasattr(dispatcherd.config, "_configured") and dispatcherd.config._configured:
            logger.debug("Dispatcherd already configured")
            return

        config_file = get_config_file_path()

        # Fall back to Django settings when the configured file is absent.
        if config_file.exists():
            # Load config file and merge with dispatcherd SQL Server settings
            logger.info(f"Loading dispatcherd config from file: {config_file}")
            config = _load_config_with_dispatcherd_settings(config_file)
        else:
            # Build config entirely from Django settings
            logger.info("Configuration file not found, using Django settings")
            config = build_config_from_settings()

        # Configure dispatcherd with the merged config
        dispatcherd.config.setup(config)

        # Mark as configured
        dispatcherd.config._configured = True
        logger.info("Dispatcherd configuration completed successfully")

    except ImportError as e:
        logger.error(f"Failed to import dispatcherd: {e}")
        raise
    except Exception as e:
        logger.exception(f"Failed to configure dispatcherd: {e}")
        raise


def _get_dispatcherd_sqlserver_config(django_settings) -> dict[str, Any]:
    """Normalize Dynaconf's case-preserving nested environment keys for pyodbc."""
    return {str(key).lower(): value for key, value in django_settings.DISPATCHERD_SQLSERVER.items()}


def _load_config_with_dispatcherd_settings(config_file: Path) -> dict[str, Any]:
    """
    Load dispatcherd config from YAML and inject the independent SQL Server broker settings.

    Args:
        config_file: Path to the dispatcherd YAML configuration file

    Returns:
        Configuration dictionary with SQL Server broker settings from Django settings
    """
    import yaml
    from django.conf import settings as django_settings

    # Load the YAML config file
    with open(config_file) as f:
        config = yaml.safe_load(f) or {}

    # Copy broker settings so dispatcherd setup does not mutate Django settings.
    sql_server_config = _get_dispatcherd_sqlserver_config(django_settings)

    # Metrics-service is fully switched to SQL Server for dispatch in this phase.
    brokers = config.setdefault("brokers", {})
    postgres_broker = brokers.pop("pg_notify", {}) or {}
    sql_server_broker = brokers.setdefault("sql_server", {})
    sql_server_broker["config"] = sql_server_config
    # Preserve broker-neutral routing options from existing PostgreSQL-only config files.
    for key in ("channels", "default_publish_channel"):
        if key not in sql_server_broker and key in postgres_broker:
            sql_server_broker[key] = postgres_broker[key]
    sql_server_broker.setdefault("channels", DEFAULT_CHANNELS.copy())

    publish = config.setdefault("publish", {})
    publish["default_broker"] = "sql_server"
    if publish.get("default_control_broker") == "pg_notify":
        publish["default_control_broker"] = "sql_server"

    # Override task timeout with Django setting
    config.setdefault("service", {}).setdefault("task_settings", {})["default_timeout"] = django_settings.TASK_TIMEOUT

    logger.info(
        "Configured dispatcherd with SQL Server broker settings: "
        f"{sql_server_config.get('server')}:{sql_server_config.get('port')}/{sql_server_config.get('database')}"
    )

    return config


def build_config_from_settings() -> dict[str, Any]:
    """
    Build dispatcherd configuration from Django settings without using DATABASES.

    Returns:
        Dictionary containing dispatcherd configuration
    """
    try:
        from django.conf import settings as django_settings

        sql_server_config = _get_dispatcherd_sqlserver_config(django_settings)

        # Build dispatcherd configuration
        config = {
            "version": 2,
            "brokers": {
                "sql_server": {
                    "config": sql_server_config,
                    "channels": DEFAULT_CHANNELS.copy(),
                },
            },
            "service": {
                "pool_kwargs": {"max_workers": 4},
                "task_settings": {
                    "default_timeout": django_settings.TASK_TIMEOUT,
                },
            },
            "publish": {"default_broker": "sql_server"},
        }

        logger.info(
            "Built dispatcherd config for SQL Server broker: "
            f"{sql_server_config.get('server')}:{sql_server_config.get('port')}/{sql_server_config.get('database')}"
        )
        return config

    except Exception as e:
        logger.exception(f"Failed to build config from Django settings: {e}")
        raise


def ensure_dispatcherd_configured() -> None:
    """
    Ensure dispatcherd is configured before attempting to submit tasks.

    This is a convenience function that should be called before any
    dispatcherd operations like submit_task().
    """
    try:
        import dispatcherd.config

        # Check if dispatcherd is configured
        if not hasattr(dispatcherd.config, "_configured") or not dispatcherd.config._configured:
            logger.info("Dispatcherd not configured, setting up configuration...")
            setup_dispatcherd_config()

    except ImportError:
        logger.error("Dispatcherd not available")
        raise
    except Exception as e:
        logger.exception(f"Failed to ensure dispatcherd configuration: {e}")
        raise
