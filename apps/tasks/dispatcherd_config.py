"""
Dispatcherd configuration utilities for metrics service.

This module provides utilities for configuring dispatcherd across different
processes and components of the metrics service.
"""

import logging
import os
from pathlib import Path
from typing import Dict, Any

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
            os.environ["DISPATCHERD_CONFIG_FILE"] = str(config_file)
            dispatcherd.config.setup()
        else:
            # Fallback to Django settings-based configuration
            logger.info("Configuration file not found, using Django settings")
            config = build_config_from_django_settings()
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


def build_config_from_django_settings() -> Dict[str, Any]:
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


def update_config_with_database_settings() -> None:
    """
    Update the dispatcherd YAML config file with current Django database settings.

    This function reads the current Django database configuration and updates
    the dispatcherd.yaml file with the correct database connection parameters.
    """
    try:
        import yaml
        from django.conf import settings as django_settings

        config_file = get_config_file_path()

        # Read existing config
        if config_file.exists():
            with open(config_file, "r") as f:
                config = yaml.safe_load(f)
        else:
            config = {}

        # Get Django database settings
        db_config = django_settings.DATABASES["default"]

        # Update database connection in config
        if "brokers" not in config:
            config["brokers"] = {}
        if "pg_notify" not in config["brokers"]:
            config["brokers"]["pg_notify"] = {}

        config["brokers"]["pg_notify"]["config"] = {
            "dbname": db_config["NAME"],
            "user": db_config["USER"],
            "password": db_config["PASSWORD"],
            "host": db_config["HOST"],
            "port": db_config["PORT"],
        }

        # Ensure config directory exists
        config_file.parent.mkdir(parents=True, exist_ok=True)

        # Write updated config
        with open(config_file, "w") as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=False)

        logger.info(f"Updated dispatcherd config file: {config_file}")

    except ImportError:
        logger.error("PyYAML not available for config file updates")
        raise
    except Exception as e:
        logger.error(f"Failed to update config file: {e}")
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
