"""
Task groups configuration for organized task management.

This module defines task groups with feature enabled controls and provides
a centralized way to manage different categories of tasks.

Feature enabled settings are stored in the database using the Setting model, allowing
runtime configuration without code changes. Values fall back to Django
settings if not found in the database.

run `manage.py metrics_utility init-system-tasks` to update the DB from `TASK_GROUPS`
"""

import json
import logging
from typing import Any

from django.conf import settings

logger = logging.getLogger(__name__)


def get_feature_enabled_from_db(setting_name: str, default: bool = False) -> bool:
    """
    Get a feature enabled value from database settings.

    Args:
        setting_name: Name of the feature enabled setting
        default: Default value if not found in database

    Returns:
        bool: Feature enabled value from database or default
    """
    try:
        # Avoid circular import by importing here
        from apps.dynamic_settings.models import Setting

        setting = Setting.objects.filter(setting_key=setting_name).first()
        if setting and setting.current_value:
            try:
                # Parse JSON value from database
                value = json.loads(setting.current_value)
                return bool(value)
            except (json.JSONDecodeError, ValueError):
                # If not valid JSON, treat as string boolean
                return setting.current_value.lower() in ("true", "1", "yes", "on")

        # Fallback to Django settings
        feature_enabled = getattr(settings, "FEATURE_ENABLED", {})
        return feature_enabled.get(setting_name, default)

    except Exception as e:
        logger.warning(f"Error reading feature enabled setting {setting_name} from database: {e}")
        # Fallback to Django settings
        feature_enabled = getattr(settings, "FEATURE_ENABLED", {})
        return feature_enabled.get(setting_name, default)


class TaskGroup:
    """
    Represents a group of related tasks with feature enabled control.
    """

    def __init__(
        self,
        name: str,
        description: str,
        enabled_setting: str = None,
        default_enabled: bool = True,
        tasks: list[dict[str, Any]] = None,
    ):
        """
        Initialize a task group.

        Args:
            name: Unique name for the task group
            description: Human-readable description
            enabled_setting: Feature enabled setting name to control this group
            default_enabled: Default state if feature enabled setting not set
            tasks: List of task configurations in this group
        """
        self.name = name
        self.description = description
        self.enabled_setting = enabled_setting
        self.default_enabled = default_enabled
        self.tasks = tasks or []

    def is_enabled(self) -> bool:
        """
        Check if this task group is enabled based on feature enabled settings.

        Feature enabled settings are read from database first, with fallback to
        Django settings if not found in database.

        Returns:
            bool: True if group is enabled, False otherwise
        """
        if not self.enabled_setting:
            return self.default_enabled

        return get_feature_enabled_from_db(self.enabled_setting, self.default_enabled)

    def get_enabled_tasks(self) -> list[dict[str, Any]]:
        """
        Get all tasks in this group that should be active.

        Returns:
            List of task configurations if group is enabled, empty list otherwise
        """
        if not self.is_enabled():
            return []

        return [task for task in self.tasks if task.get("enabled", True)]


# System Tasks Group - Always enabled, core system maintenance
SYSTEM_TASKS_GROUP = TaskGroup(
    name="system_tasks",
    description="Core system maintenance tasks that are always enabled",
    enabled_setting=None,  # Always enabled
    default_enabled=True,
    tasks=[
        {
            "task_id": "daily_task_cleanup",
            "function": "cleanup_old_tasks",
            "cron": "0 2 * * *",  # Daily at 2 AM
            "args": {
                "days_old": 5,
                "dry_run": False,
                "include_executions": True,
                "preserve_recurring": True,
            },
            "enabled": True,
            "description": "Daily cleanup of old completed/failed tasks (preserves recurring tasks)",
            "category": "maintenance",
        },
        {
            "task_id": "weekly_data_cleanup",
            "function": "cleanup_old_data",
            "cron": "0 3 * * 0",  # Weekly on Sunday at 3 AM
            "args": {"days_old": 30, "data_types": ["logs", "temp_files", "cache"]},
            "enabled": True,
            "description": "Weekly cleanup of old system data and temporary files",
            "category": "maintenance",
        },
        {
            "task_id": "hourly_health_check",
            "function": "hello_world",
            "cron": "0 * * * *",  # Every hour
            "args": {},
            "enabled": True,
            "description": "Hourly system health check",
            "category": "monitoring",
        },
    ],
)

# Anonymized Data Collection Group - Controlled by feature enabled setting
ANONYMIZED_DATA_GROUP = TaskGroup(
    name="anonymized_data",
    description="Anonymized data collection tasks",
    enabled_setting="ANONYMIZED_DATA_COLLECTION",
    default_enabled=True,  # Default enabled but can be controlled
    tasks=[
        {
            "task_id": "full_process_anonymize",
            "function": "full_process_anonymize",
            "cron": "0 */12 * * *",  # Every 12 hours
            "args": {},
            "enabled": True,
            "description": "Collect anonymized metrics and send directly to Segment.com",
            "category": "anonymous_metrics",
        },
    ],
)

# Metrics Collection Group - Customer controlled
METRICS_COLLECTION_GROUP = TaskGroup(
    name="metrics_collection",
    description="Customer-controlled metrics collection tasks",
    enabled_setting="METRICS_COLLECTION_ENABLED",
    default_enabled=False,  # Customers must explicitly enable
    tasks=[
        {
            "task_id": "collect_all_metrics_daily",
            "function": "collect_metrics",  # Changed from collect_all_metrics to collect_metrics
            "cron": "0 1 * * *",  # Daily at 1 AM
            "args": {"collectors": ["anonymized_rollups", "config", "job_host_summary", "main_host", "main_jobevent"]},
            "enabled": True,
            "description": "Daily comprehensive metrics collection using all collectors",
            "category": "metrics_collection",
        },
    ],
)

# Hourly Metrics Collection Group - Customer controlled, hourly granularity with daily rollup
HOURLY_METRICS_GROUP = TaskGroup(
    name="hourly_metrics",
    description="Hourly metrics collection with daily rollup and anonymization",
    enabled_setting="METRICS_COLLECTION_ENABLED",
    default_enabled=False,  # Disabled by default, customer opt-in required
    tasks=[
        # Hourly Collection Tasks
        {
            "task_id": "hourly_job_host_summary",
            "function": "collect_job_host_summary_hourly",
            "cron": "5 * * * *",  # Every hour at XX:05
            "args": {},
            "enabled": True,
            "description": "Collect job host summary metrics every hour",
            "category": "hourly_collection",
        },
        {
            "task_id": "hourly_host_metrics",
            "function": "collect_host_metrics_hourly",
            "cron": "10 * * * *",  # Every hour at XX:10
            "args": {},
            "enabled": True,
            "description": "Collect host metrics every hour",
            "category": "hourly_collection",
        },
        {
            "task_id": "hourly_main_host",
            "function": "collect_main_host_hourly",
            "cron": "15 * * * *",  # Every hour at XX:15
            "args": {},
            "enabled": True,
            "description": "Collect main_host metrics every hour",
            "category": "hourly_collection",
        },
        # Daily Rollup Tasks
        {
            "task_id": "daily_metrics_rollup",
            "function": "daily_metrics_rollup",
            "cron": "0 2 * * *",  # Daily at 2:00 AM
            "args": {},
            "enabled": True,
            "description": "Create daily rollup from hourly collections",
            "category": "daily_rollup",
        },
        {
            "task_id": "daily_anonymize",
            "function": "daily_anonymize_and_prepare",
            "cron": "0 3 * * *",  # Daily at 3:00 AM
            "args": {},
            "enabled": True,
            "description": "Anonymize daily summary for Segment transmission",
            "category": "daily_anonymization",
        },
        {
            "task_id": "send_to_segment_daily",
            "function": "send_anonymized_to_segment",
            "cron": "30 3 * * *",  # Daily at 3:30 AM
            "args": {},
            "enabled": True,
            "description": "Send anonymized payloads to Segment",
            "category": "daily_send",
        },
        # Cleanup Task
        {
            "task_id": "cleanup_metrics_data",
            "function": "cleanup_metrics_data",
            "cron": "0 4 * * *",  # Daily at 4:00 AM
            "args": {
                "hourly_retention_days": 7,
                "daily_retention_days": 30,
                "payload_retention_days": 7,
            },
            "enabled": True,
            "description": "Clean up old metrics data based on retention policies",
            "category": "maintenance",
        },
    ],
)

# Registry of all task groups
TASK_GROUPS = [
    SYSTEM_TASKS_GROUP,
    ANONYMIZED_DATA_GROUP,
    METRICS_COLLECTION_GROUP,
    HOURLY_METRICS_GROUP,
]


def get_all_enabled_tasks() -> dict[str, dict[str, Any]]:
    """
    Get all enabled tasks from all groups.

    Returns:
        Dictionary mapping task_id to task configuration for all enabled tasks.
        Each task config includes the feature_flag from its group for runtime checking.
    """
    all_tasks = {}

    for group in TASK_GROUPS:
        enabled_tasks = group.get_enabled_tasks()
        for task in enabled_tasks:
            task_id = task["task_id"]
            task_config = task.copy()
            task_config["group"] = group.name
            task_config["group_description"] = group.description
            # Add feature flag for runtime checking
            task_config["feature_flag"] = group.enabled_setting
            all_tasks[task_id] = task_config

    return all_tasks
