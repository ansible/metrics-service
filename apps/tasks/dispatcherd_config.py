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

    # Default to config/dispatcherd.yaml in project root
    project_root = Path(__file__).parent.parent.parent
    return project_root / "config" / "dispatcherd.yaml"


def fallback_dispatcherd_config() -> dict[str, Any]:
    return {
        "version": 2,
        "brokers": {
            "pg_notify": {
                "config": None,
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


def load_dispatcherd_config(path) -> dict[str, Any]:
    import yaml

    try:
        with open(path) as f:
            return yaml.safe_load(f)
    except Exception:
        logger.warning(f"Failed to load configuration from {path}, using default")
        return fallback_dispatcherd_config()


def pg_config_from_django_settings() -> dict[str, Any]:
    """
    Build dispatcherd .brokers.pg_notify.config configuration fragment from Django database settings.
    """
    from django.conf import settings as django_settings

    # Get database configuration
    db_config = django_settings.DATABASES["default"]

    # Create PostgreSQL connection config
    return {
        "dbname": db_config["NAME"],
        "user": db_config["USER"],
        "password": db_config["PASSWORD"],
        "host": db_config["HOST"],
        "port": db_config["PORT"],
    }


def setup_dispatcherd_config() -> None:
    """
    Setup dispatcherd configuration from file or Django settings.

    This function configures dispatcherd to work with the metrics service
    database and task queues. It can be called from any process that needs
    to submit tasks to dispatcherd.
    """
    try:
        import dispatcherd.config

        # Check if already configured
        if hasattr(dispatcherd.config, "_configured") and dispatcherd.config._configured:
            logger.debug("Dispatcherd already configured")
            return

        config_file = get_config_file_path()

        if config_file.exists():
            # Use configuration file
            logger.info(f"Configuring dispatcherd from file: {config_file}")
            config = load_dispatcherd_config(config_file)
        else:
            # Fallback to Django settings-based configuration
            logger.info("Configuration file not found, using fallback")
            config = fallback_dispatcherd_config()

        # Update database connection in config
        if "brokers" not in config:
            config["brokers"] = {}
        if "pg_notify" not in config["brokers"]:
            config["brokers"]["pg_notify"] = {}
        if "config" not in config["brokers"]["pg_notify"]:
            config["brokers"]["pg_notify"]["config"] = None

        # Update from Django settings
        if config["brokers"]["pg_notify"]["config"] is None:
            pg_config = pg_config_from_django_settings()
            config["brokers"]["pg_notify"]["config"] = pg_config
            logger.info(
                f"Updated dispatcherd config for database: {pg_config['host']}:{pg_config['port']}/{pg_config['dbname']}"
            )

        # Setup dispatcherd
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


# FIXME: duplicate of setup_dispatcherd_config - merge
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


def get_queue_for_function(function_name: str) -> str:
    """
    Get the appropriate queue name for a task function.

    Args:
        function_name: Name of the task function

    Returns:
        Queue name to submit the task to
    """
    queue_mapping = {
        "hello_world": "metrics_tasks",
        "cleanup_old_data": "metrics_cleanup",
        "cleanup_old_tasks": "metrics_cleanup",
        "send_notification_email": "metrics_notifications",
        "process_user_data": "metrics_tasks",
        "execute_db_task": "metrics_tasks",
        "sleep": "metrics_tasks",
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
