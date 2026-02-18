"""
Background tasks for metrics_service using dispatcherd.

This module serves as an aggregator, importing and re-exporting tasks from
individual task modules organized by queue:
- simple/: Simple system tasks (metrics_tasks queue)
- cleanup/: Cleanup and maintenance tasks (metrics_cleanup queue)
- collectors/: Metrics collection and anonymization tasks (metrics_collectors queue)
- tasks_system: Core task execution infrastructure and utilities
"""

import logging

# Import cleanup tasks
from .cleanup.cleanup_metrics_data import cleanup_metrics_data
from .cleanup.cleanup_old_tasks import cleanup_old_tasks

# Import collector tasks
from .collectors.collect_host_metrics_hourly import collect_host_metrics_hourly
from .collectors.collect_job_host_summary_hourly import collect_job_host_summary_hourly
from .collectors.collect_main_host_hourly import collect_main_host_hourly
from .collectors.daily_anonymize_and_prepare import daily_anonymize_and_prepare
from .collectors.daily_metrics_rollup import daily_metrics_rollup
from .collectors.send_anonymized_to_segment import send_anonymized_to_segment

# Import system tasks
from .simple.hello_world import hello_world
from .tasks_system import (
    create_system_tasks,
    execute_db_task,
    get_system_task_info,
    submit_task_to_dispatcher,
)

logger = logging.getLogger(__name__)

# Task configuration for dispatcherd
TASK_FUNCTIONS = {
    # System tasks
    "hello_world": hello_world,
    "cleanup_old_tasks": cleanup_old_tasks,
    "cleanup_metrics_data": cleanup_metrics_data,
    "execute_db_task": execute_db_task,
    # Hourly Metrics Collection Tasks (MAP phase)
    "collect_job_host_summary_hourly": collect_job_host_summary_hourly,
    "collect_host_metrics_hourly": collect_host_metrics_hourly,
    "collect_main_host_hourly": collect_main_host_hourly,
    # Daily Rollup and Anonymization Tasks (REDUCE + ANONYMIZE + SEND)
    "daily_metrics_rollup": daily_metrics_rollup,
    "daily_anonymize_and_prepare": daily_anonymize_and_prepare,
    "send_anonymized_to_segment": send_anonymized_to_segment,
}

# Enhanced task metadata for dashboard display
TASK_METADATA = {
    # Testing
    "hello_world": {
        "category": "Testing",
        "description": "Simple hello world task for testing the dispatcherd integration",
        "parameters": {},
        "examples": [{"name": "Basic Hello World", "data": {}}],
    },
    # Maintenance
    "cleanup_old_tasks": {
        "category": "Maintenance",
        "description": "Clean up old completed and failed tasks (preserves recurring tasks by default)",
        "parameters": {
            "days_old": {
                "type": "integer",
                "default": 5,
                "description": "Number of days old tasks should be to qualify for cleanup",
                "min": 1,
                "max": 365,
            },
            "dry_run": {
                "type": "boolean",
                "default": False,
                "description": "If true, only count tasks that would be deleted without actually deleting",
            },
            "include_executions": {
                "type": "boolean",
                "default": True,
                "description": "Also cleanup related TaskExecution records",
            },
            "preserve_recurring": {
                "type": "boolean",
                "default": True,
                "description": "If true, exclude recurring tasks from cleanup (recommended)",
            },
        },
        "examples": [
            {"name": "Standard cleanup (5 days)", "data": {"days_old": 5}},
            {"name": "Test cleanup (dry run)", "data": {"days_old": 7, "dry_run": True}},
            {"name": "Conservative cleanup", "data": {"days_old": 10, "include_executions": False}},
        ],
    },
    # System
    "execute_db_task": {
        "category": "System",
        "description": "Execute a database-defined task with comprehensive lifecycle management",
        "parameters": {
            "task_id": {"type": "integer", "required": True, "description": "ID of the task to execute"},
            "execution_id": {"type": "integer", "description": "ID of the execution record (optional)"},
        },
        "examples": [{"name": "Execute task by ID", "data": {"task_id": 123}}],
    },
}

# Explicit exports for better IDE support
__all__ = [
    # System tasks
    "hello_world",
    "cleanup_old_tasks",
    "cleanup_metrics_data",
    "execute_db_task",
    "submit_task_to_dispatcher",
    "create_system_tasks",
    "get_system_task_info",
    # Hourly collection tasks (MAP phase)
    "collect_job_host_summary_hourly",
    "collect_host_metrics_hourly",
    "collect_main_host_hourly",
    # Daily rollup and anonymization tasks (REDUCE + ANONYMIZE + SEND)
    "daily_metrics_rollup",
    "daily_anonymize_and_prepare",
    "send_anonymized_to_segment",
    # Configuration
    "TASK_FUNCTIONS",
    "TASK_METADATA",
]
