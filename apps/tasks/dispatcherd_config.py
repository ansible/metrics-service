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
    database and task queues. It can be called from any process that needs
    to submit tasks to dispatcherd.

    Database connection settings always come from Django's DATABASES["default"]
    which properly respects METRICS_SERVICE_DATABASES__default__* environment
    variables. The YAML config file is used for other settings (channels,
    queue routing, logging, etc.).
    """
    try:
        import dispatcherd.config

        # Check if already configured
        if hasattr(dispatcherd.config, "_configured") and dispatcherd.config._configured:
            logger.debug("Dispatcherd already configured")
            return

        config_file = get_config_file_path()

        if config_file.exists():
            # Load config file and merge with Django database settings
            logger.info(f"Loading dispatcherd config from file: {config_file}")
            config = _load_config_with_django_db(config_file)
        else:
            # Build config entirely from Django settings
            logger.info("Configuration file not found, using Django settings")
            config = build_config_from_django_settings()

        # Configure dispatcherd with the merged config
        dispatcherd.config.setup(config)

        # Mark as configured
        dispatcherd.config._configured = True
        logger.info("Dispatcherd configuration completed successfully")

    except ImportError as e:
        logger.error(f"Failed to import dispatcherd: {e}")
        raise
    except Exception as e:
        logger.error(f"Failed to configure dispatcherd: {e}")
        raise


def _load_config_with_django_db(config_file: Path) -> dict[str, Any]:
    """
    Load dispatcherd config from YAML file but override database settings
    with Django's DATABASES["default"] configuration.

    This ensures database connection settings always come from Django settings
    which properly respects METRICS_SERVICE_DATABASES__default__* environment
    variables via Dynaconf.

    Args:
        config_file: Path to the dispatcherd YAML configuration file

    Returns:
        Configuration dictionary with database settings from Django
    """
    import yaml
    from django.conf import settings as django_settings

    # Load the YAML config file
    with open(config_file) as f:
        config = yaml.safe_load(f) or {}

    # Get database configuration from Django settings
    db_config = django_settings.DATABASES["default"]

    # Build PostgreSQL connection config from Django settings
    pg_config = {
        "dbname": db_config["NAME"],
        "user": db_config["USER"],
        "password": db_config["PASSWORD"],
        "host": db_config["HOST"],
        "port": db_config["PORT"],
    }

    # Ensure brokers section exists
    if "brokers" not in config:
        config["brokers"] = {}
    if "pg_notify" not in config["brokers"]:
        config["brokers"]["pg_notify"] = {}

    # Override database config with Django settings
    config["brokers"]["pg_notify"]["config"] = pg_config

    logger.info(
        f"Configured dispatcherd with Django database settings: "
        f"{pg_config['host']}:{pg_config['port']}/{pg_config['dbname']}"
    )

    return config


def build_config_from_django_settings() -> dict[str, Any]:
    """
    Build dispatcherd configuration from Django database settings.

    Returns:
        Dictionary containing dispatcherd configuration
    """
    try:
        from django.conf import settings as django_settings

        # Get database configuration
        db_config = django_settings.DATABASES["default"]

        # Create PostgreSQL connection config
        pg_config = {
            "dbname": db_config["NAME"],
            "user": db_config["USER"],
            "password": db_config["PASSWORD"],
            "host": db_config["HOST"],
            "port": db_config["PORT"],
        }

        # Build dispatcherd configuration
        config = {
            "version": 2,
            "brokers": {
                "pg_notify": {
                    "config": pg_config,
                    "channels": [
                        "metrics_tasks",
                        "metrics_cleanup",
                        "metrics_notifications",
                        "metrics_collectors",
                        "metrics_utility",
                    ],
                },
            },
            "service": {
                "pool_kwargs": {"max_workers": 4},
            },
        }

        logger.info(
            f"Built dispatcherd config for database: {pg_config['host']}:{pg_config['port']}/{pg_config['dbname']}"
        )
        return config

    except Exception as e:
        logger.error(f"Failed to build config from Django settings: {e}")
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
        logger.error(f"Failed to ensure dispatcherd configuration: {e}")
        raise


# FIXME duplicate impls
def get_queue_for_function(function_name: str) -> str:
    """
    Get the appropriate queue name for a task function.

    Args:
        function_name: Name of the task function

    Returns:
        Queue name to submit the task to
    """
    queue_mapping = {
        # System/general tasks
        "hello_world": "metrics_tasks",
        "execute_db_task": "metrics_tasks",
        "sleep": "metrics_tasks",
        # Cleanup tasks
        "cleanup_old_data": "metrics_cleanup",
        "cleanup_old_tasks": "metrics_cleanup",
        "cleanup_metrics_data": "metrics_cleanup",
        # Hourly collection tasks
        "collect_job_host_summary_hourly": "metrics_collectors",
        "collect_host_metrics_hourly": "metrics_collectors",
        "collect_main_host_hourly": "metrics_collectors",
        # Daily rollup and anonymization tasks
        "daily_metrics_rollup": "metrics_collectors",
        "daily_anonymize_and_prepare": "metrics_collectors",
        "send_anonymized_to_segment": "metrics_collectors",
        # Unified collector tasks
        "collect_single_collector": "metrics_collectors",
        "collect_metrics": "metrics_collectors",
        "anonymize_data": "metrics_collectors",
        "send_to_segment": "metrics_collectors",
        "full_process": "metrics_collectors",
        "full_process_anonymize": "metrics_collectors",
        # Legacy metrics collection task names (backward compatibility)
        "collect_anonymous_metrics": "metrics_collectors",
        "collect_config_metrics": "metrics_collectors",
        "collect_job_host_summary": "metrics_collectors",
        "collect_host_metrics": "metrics_collectors",
        "collect_all_metrics": "metrics_collectors",
        # Metrics-utility tasks
        "gather_automation_controller_billing_data": "metrics_utility",
        "build_metrics_report": "metrics_utility",
        "metrics_utility_health_check": "metrics_utility",
        "metrics_utility_custom_command": "metrics_utility",
    }

    return queue_mapping.get(function_name, "metrics_tasks")
