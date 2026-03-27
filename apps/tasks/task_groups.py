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
    Represents a group of related tasks with optional feature flag control.

    Task groups can have a feature_flag that controls all tasks in the group.
    Individual tasks can be disabled via the 'enabled' field regardless of the group's feature flag.
    """

    def __init__(
        self,
        name: str,
        description: str,
        tasks: list[dict[str, Any]] = None,
        feature_flag: str | None = None,
    ):
        """
        Initialize a task group.

        Args:
            name: Unique name for the task group
            description: Human-readable description
            tasks: List of task configurations in this group
            feature_flag: Optional feature flag name that controls this entire group
        """
        self.name = name
        self.description = description
        self.tasks = tasks or []
        self.feature_flag = feature_flag

    def get_enabled_tasks(self) -> list[dict[str, Any]]:
        """
        Get all tasks in this group that should be active.

        First checks the group-level feature flag (if present).
        Then filters out tasks with enabled=False.

        Feature flag defaults are defined in Django settings (FEATURE_ENABLED dict).

        Returns:
            List of task configurations that are enabled
        """
        # Check group-level feature flag first
        if self.feature_flag and not get_feature_enabled_from_db(self.feature_flag):
            return []

        # Filter tasks by their individual enabled field
        enabled_tasks = [task for task in self.tasks if task.get("enabled", True)]

        return enabled_tasks


# System Tasks Group - Always enabled, core system maintenance
SYSTEM_TASKS_GROUP = TaskGroup(
    name="system_tasks",
    description="Core system maintenance tasks that are always enabled",
    tasks=[
        {
            "task_id": "daily_task_cleanup",
            "function": "cleanup_old_tasks",
            "cron": "0 5 * * *",  # Daily at 5 AM
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

# Metrics Collection Group - Always enabled, no feature flag.
# Raw collection, rollup, and cleanup run regardless of the ANONYMIZED_DATA_COLLECTION flag.
# Operators who opt out of sending data to Red Hat will still collect local metrics
# to prevent a data gap if sending is enabled later.
METRICS_COLLECTION_GROUP = TaskGroup(
    name="metrics_collection",
    description="Metrics collection, rollup, and cleanup (always enabled)",
    tasks=[
        # Hourly Collection Tasks
        {
            "task_id": "hourly_job_host_summary",
            "function": "collect_hourly_metrics",
            "cron": "5 * * * *",  # Every hour at XX:05
            "args": {"collector_type": "job_host_summary_service"},
            "enabled": True,
            "description": "Collect job host summary metrics every hour (service variant)",
            "category": "hourly_collection",
        },
        {
            "task_id": "hourly_unified_jobs",
            "function": "collect_hourly_metrics",
            "cron": "10 * * * *",  # Every hour at XX:10
            "args": {"collector_type": "unified_jobs"},
            "enabled": True,
            "description": "Collect unified jobs metrics every hour",
            "category": "hourly_collection",
        },
        {
            "task_id": "hourly_credentials",
            "function": "collect_hourly_metrics",
            "cron": "15 * * * *",  # Every hour at XX:15
            "args": {"collector_type": "credentials_service"},
            "enabled": True,
            "description": "Collect credentials metrics every hour",
            "category": "hourly_collection",
        },
        {
            "task_id": "hourly_job_events",
            "function": "collect_hourly_metrics",
            "cron": "20 * * * *",  # Every hour at XX:20
            "args": {"collector_type": "main_jobevent_service"},
            "enabled": False,  # NOT enabled by default, for performance
            "description": "Collect job events (event modules) metrics every hour",
            "category": "hourly_collection",
        },
        # Daily Snapshot Collection
        {
            "task_id": "daily_execution_environments",
            "function": "collect_snapshot_metrics",
            "cron": "0 1 * * *",  # Daily at 1:00 AM
            "args": {"collector_type": "execution_environments"},
            "enabled": True,
            "description": "Collect execution environments snapshot daily",
            "category": "daily_collection",
        },
        {
            "task_id": "daily_config",
            "function": "collect_snapshot_metrics",
            "cron": "30 1 * * *",  # Daily at 1:30 AM
            "args": {"collector_type": "config"},
            "enabled": True,
            "description": "Collect system configuration snapshot daily",
            "category": "daily_collection",
        },
        {
            "task_id": "daily_controller_version",
            "function": "collect_snapshot_metrics",
            "cron": "35 1 * * *",  # Daily at 1:35 AM
            "args": {"collector_type": "controller_version_service"},
            "enabled": True,
            "description": "Collect controller version snapshot daily",
            "category": "daily_collection",
        },
        {
            "task_id": "daily_table_metadata",
            "function": "collect_snapshot_metrics",
            "cron": "40 1 * * *",  # Daily at 1:40 AM
            "args": {"collector_type": "table_metadata"},
            "enabled": True,
            "description": "Collect table metadata snapshot daily",
            "category": "daily_collection",
        },
        {
            "task_id": "daily_feature_flags",
            "function": "collect_snapshot_metrics",
            "cron": "45 1 * * *",  # Daily at 1:45 AM
            "args": {"collector_type": "feature_flags_service"},
            "enabled": True,
            "description": "Collect feature flags snapshot daily",
            "category": "daily_collection",
        },
        {
            "task_id": "daily_task_executions",
            "function": "collect_daily_metrics",
            "cron": "50 1 * * *",  # Daily at 1:50 AM — after snapshots (1:45 AM), before rollup (2:00 AM)
            "args": {"collector_type": "task_executions_service"},
            "enabled": True,
            "description": "Collect task execution observability metrics for the previous day (pipeline health)",
            "category": "daily_collection",
        },
        # Daily Rollup
        {
            "task_id": "daily_metrics_rollup",
            "function": "daily_metrics_rollup",
            "cron": "0 2 * * *",  # Daily at 2:00 AM
            "args": {},
            "enabled": True,
            "description": "Create daily rollup from hourly collections",
            "category": "daily_rollup",
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

# Anonymization Group - Controlled by ANONYMIZED_DATA_COLLECTION.
# Only these two tasks are gated by the flag, disabling it stops data being sent to Red Hat
# while leaving local collection intact so there is no data gap after enabling again.
ANONYMIZATION_GROUP = TaskGroup(
    name="anonymization",
    description="Anonymization and transmission of metrics to Red Hat (opt-out via ANONYMIZED_DATA_COLLECTION)",
    feature_flag="ANONYMIZED_DATA_COLLECTION",
    tasks=[
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
    ],
)

# Dashboard Collection Group - automation-reports integration
DASHBOARD_COLLECTION_GROUP = TaskGroup(
    name="dashboard_collection",
    description="Automation-reports dashboard data collection (SQL-based, separate from anonymization)",
    feature_flag="DASHBOARD_COLLECTION",
    tasks=[
        {
            "task_id": "initial_dashboard_collection",
            "function": "collect_dashboard_reports_initial_data",
            "cron": None,  # No schedule, run once on enable
            "args": {},  # Uses incremental collection by default to minimize load
            "enabled": True,
            "description": "Initial dashboard report collection",
            "category": "dashboard_collection",
        },
        {
            "task_id": "daily_dashboard_collection",
            "function": "collect_dashboard_reports_data",
            "cron": "0 */6 * * *",  # Runs every 6 hours (at minute 0)
            "args": {"incremental": True},  # Uses incremental collection by default to minimize load
            "enabled": False,
            "description": "Dashboard report collection every 6 hours",
            "category": "dashboard_collection",
        },
        {
            "task_id": "cleanup_dashboard_reports_old_data",
            "function": "cleanup_dashboard_reports_old_data",
            "cron": "0 5 * * *",  # Daily at 5:00 AM
            "args": {
                "retention_days": 90,
            },
            "enabled": True,
            "description": "Clean up old dashboard report data based on retention policy",
            "category": "maintenance",
        },
    ],
)

# Registry of all task groups
TASK_GROUPS = [
    SYSTEM_TASKS_GROUP,
    METRICS_COLLECTION_GROUP,
    ANONYMIZATION_GROUP,
    DASHBOARD_COLLECTION_GROUP,
]


def get_all_enabled_tasks() -> dict[str, dict[str, Any]]:
    """
    Get all enabled tasks from all groups.

    Group-level feature flags are evaluated at call, so tasks whose group flag
    is disabled are excluded. Use get_all_tasks_for_init() when you need
    all tasks unconditionally.

    Returns:
        Dictionary mapping task_id to task configuration for all enabled tasks.
        Each task config includes the group's feature_flag (if any) for runtime checking.
    """
    all_tasks = {}

    for group in TASK_GROUPS:
        enabled_tasks = group.get_enabled_tasks()
        for task in enabled_tasks:
            task_id = task["task_id"]
            task_config = task.copy()
            task_config["group"] = group.name
            task_config["group_description"] = group.description
            # Add group's feature flag for runtime checking
            if group.feature_flag:
                task_config["feature_flag"] = group.feature_flag
            all_tasks[task_id] = task_config

    return all_tasks


def get_all_tasks_for_init() -> dict[str, dict[str, Any]]:
    """
    Get all tasks from all groups for use by init-system-tasks.

    This function does NOT evaluate group-level feature flags.
    Every task that has enabled=True (or no enabled field) is included.
    The group's feature_flag is embedded in each task config.

    Returns:
        Dictionary mapping task_id to task configuration for all individually-enabled
        tasks across all groups, with feature_flag included where applicable.
    """
    all_tasks = {}

    for group in TASK_GROUPS:
        # Respect individual task enabled fields but ignore the group-level flag.
        individually_enabled = [task for task in group.tasks if task.get("enabled", True)]
        for task in individually_enabled:
            task_id = task["task_id"]
            task_config = task.copy()
            task_config["group"] = group.name
            task_config["group_description"] = group.description
            if group.feature_flag:
                task_config["feature_flag"] = group.feature_flag
            all_tasks[task_id] = task_config

    return all_tasks
