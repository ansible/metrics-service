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
from .collectors.collect_hourly_metrics import collect_hourly_metrics
from .collectors.collect_snapshot_metrics import collect_snapshot_metrics
from .collectors.daily_anonymize_and_prepare import daily_anonymize_and_prepare
from .collectors.daily_metrics_rollup import daily_metrics_rollup
from .collectors.send_anonymized_to_segment import send_anonymized_to_segment

# Note: Hourly and snapshot collectors handle all collector types via collector_type parameter
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
    # Metrics Collection (hourly time-series and daily snapshots)
    "collect_hourly_metrics": collect_hourly_metrics,
    "collect_snapshot_metrics": collect_snapshot_metrics,
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
    "cleanup_metrics_data": {
        "category": "Maintenance",
        "description": "Clean up old metrics data based on retention policies",
        "parameters": {
            "hourly_retention_days": {
                "type": "integer",
                "default": 7,
                "description": "Number of days to retain hourly collection data",
                "min": 1,
                "max": 365,
            },
            "daily_retention_days": {
                "type": "integer",
                "default": 30,
                "description": "Number of days to retain daily rollup data",
                "min": 1,
                "max": 730,
            },
            "payload_retention_days": {
                "type": "integer",
                "default": 7,
                "description": "Number of days to retain anonymized payloads",
                "min": 1,
                "max": 90,
            },
        },
        "examples": [
            {"name": "Default retention", "data": {}},
            {
                "name": "Custom retention",
                "data": {"hourly_retention_days": 14, "daily_retention_days": 60, "payload_retention_days": 14},
            },
        ],
    },
    # Metrics Collection (Hourly and Snapshot)
    "collect_hourly_metrics": {
        "category": "Metrics Collection",
        "description": "Collect hourly time-series metrics for a specific collector type",
        "parameters": {
            "collector_type": {
                "type": "string",
                "required": True,
                "description": "Type of collector to run (e.g., job_host_summary_service, unified_jobs, credentials_service)",
            },
            "hour_timestamp": {
                "type": "string",
                "description": "ISO timestamp for the hour to collect (defaults to current hour)",
            },
        },
        "examples": [
            {"name": "Job host summary", "data": {"collector_type": "job_host_summary_service"}},
            {"name": "Unified jobs", "data": {"collector_type": "unified_jobs"}},
            {"name": "Credentials", "data": {"collector_type": "credentials_service"}},
            {"name": "Job events", "data": {"collector_type": "main_jobevent_service"}},
            {
                "name": "Specific hour",
                "data": {"collector_type": "job_host_summary_service", "hour_timestamp": "2024-01-01T00:00:00Z"},
            },
        ],
    },
    "collect_snapshot_metrics": {
        "category": "Metrics Collection",
        "description": "Collect daily snapshot metrics for a specific collector type",
        "parameters": {
            "collector_type": {
                "type": "string",
                "required": True,
                "description": "Type of collector to run (e.g., execution_environments, config)",
            },
        },
        "examples": [
            {"name": "Execution environments", "data": {"collector_type": "execution_environments"}},
            {"name": "System config", "data": {"collector_type": "config"}},
        ],
    },
    # Daily Rollup and Anonymization
    "daily_metrics_rollup": {
        "category": "Metrics Rollup",
        "description": "Merge hourly collections and create daily rollup summary",
        "parameters": {
            "summary_date": {
                "type": "string",
                "description": "ISO date for the rollup (defaults to yesterday)",
            },
        },
        "examples": [
            {"name": "Default (yesterday)", "data": {}},
            {"name": "Specific date", "data": {"summary_date": "2024-01-01"}},
        ],
    },
    "daily_anonymize_and_prepare": {
        "category": "Metrics Anonymization",
        "description": "Anonymize daily rollup and prepare payload for transmission",
        "parameters": {
            "summary_date": {
                "type": "string",
                "description": "ISO date for the summary to anonymize (defaults to yesterday)",
            },
        },
        "examples": [
            {"name": "Default (yesterday)", "data": {}},
            {"name": "Specific date", "data": {"summary_date": "2024-01-01"}},
        ],
    },
    "send_anonymized_to_segment": {
        "category": "Metrics Transmission",
        "description": "Send anonymized metrics payloads to Segment.com",
        "parameters": {
            "summary_date": {
                "type": "string",
                "description": "ISO date for the payloads to send (defaults to yesterday)",
            },
            "dry_run": {
                "type": "boolean",
                "default": False,
                "description": "If true, prepare payloads but don't actually send to Segment",
            },
        },
        "examples": [
            {"name": "Default (yesterday)", "data": {}},
            {"name": "Specific date", "data": {"summary_date": "2024-01-01"}},
            {"name": "Dry run", "data": {"dry_run": True}},
        ],
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
    # Metrics collection (hourly and snapshot)
    "collect_hourly_metrics",
    "collect_snapshot_metrics",
    # Daily rollup and anonymization tasks (REDUCE + ANONYMIZE + SEND)
    "daily_metrics_rollup",
    "daily_anonymize_and_prepare",
    "send_anonymized_to_segment",
    # Configuration
    "TASK_FUNCTIONS",
    "TASK_METADATA",
]
