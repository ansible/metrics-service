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
from .collectors.anonymize_data import anonymize_data
from .collectors.collect_host_metrics_hourly import collect_host_metrics_hourly
from .collectors.collect_job_host_summary_hourly import collect_job_host_summary_hourly
from .collectors.collect_main_host_hourly import collect_main_host_hourly
from .collectors.collect_metrics import collect_metrics
from .collectors.collect_single_collector import collect_single_collector
from .collectors.daily_anonymize_and_prepare import daily_anonymize_and_prepare
from .collectors.daily_metrics_rollup import daily_metrics_rollup
from .collectors.full_process import full_process
from .collectors.full_process_anonymize import full_process_anonymize
from .collectors.helpers import METRICS_UTILITY_AVAILABLE
from .collectors.send_anonymized_to_segment import send_anonymized_to_segment
from .collectors.send_to_segment_task import send_to_segment_task

# Import system tasks
from .simple.hello_world import hello_world
from .tasks_system import (
    create_system_tasks,
    execute_db_task,
    get_system_task_info,
    submit_task_to_dispatcher,
)

logger = logging.getLogger(__name__)

# Constants for repeated strings (used in TASK_METADATA)
MSG_METRICS_UTILITY_NOT_AVAILABLE = "metrics-utility is not available"
LABEL_DB_CONNECTION = "Database name from Django settings (default: 'awx')"
LABEL_START_DATE = "Start date for collection (ISO format)"
LABEL_END_DATE = "End date for collection (ISO format)"
EXAMPLE_START_DATE = "2024-01-01T00:00:00Z"
DESC_SALT_ANONYMIZATION = "Salt for anonymization (auto-generated UUID4 if not provided)"
DESC_SEGMENT_WRITE_KEY = "Segment.com write key for analytics"
DESC_USER_ID_TRACKING = "User ID for tracking"
DESC_EVENT_NAME_TRACKING = "Event name for tracking"

# Task configuration for dispatcherd
TASK_FUNCTIONS = {
    # System tasks
    "hello_world": hello_world,
    "cleanup_old_tasks": cleanup_old_tasks,
    "cleanup_metrics_data": cleanup_metrics_data,
    "execute_db_task": execute_db_task,
    # Hourly Metrics Collection Tasks
    "collect_job_host_summary_hourly": collect_job_host_summary_hourly,
    "collect_host_metrics_hourly": collect_host_metrics_hourly,
    "collect_main_host_hourly": collect_main_host_hourly,
    # Daily Rollup and Anonymization Tasks
    "daily_metrics_rollup": daily_metrics_rollup,
    "daily_anonymize_and_prepare": daily_anonymize_and_prepare,
    "send_anonymized_to_segment": send_anonymized_to_segment,
    # Metrics Collection Tasks (unified collectors)
    "collect_single_collector": collect_single_collector,
    "collect_metrics": collect_metrics,
    "anonymize_data": anonymize_data,
    "send_to_segment": send_to_segment_task,
    "full_process": full_process,
    "full_process_anonymize": full_process_anonymize,
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
    # Controller - anonymized metrics
    "collect_single_collector": {
        "category": "Controller metrics",
        "description": "Unified task to collect data from a single collector with configurable output format",
        "parameters": {
            "collector_type": {
                "type": "string",
                "required": True,
                "description": "Collector to run",
                "choices": ["anonymized_rollups", "config", "job_host_summary", "main_host", "main_jobevent"],
            },
            "database": {"type": "string", "description": LABEL_DB_CONNECTION},
            "since": {"type": "string", "description": LABEL_START_DATE, "pattern": "datetime"},
            "until": {"type": "string", "description": LABEL_END_DATE, "pattern": "datetime"},
            "salt": {"type": "string", "description": DESC_SALT_ANONYMIZATION},
            "output_format": {
                "type": "string",
                "default": "json",
                "description": "Output format: 'json' (converted) or 'csv' (raw file paths)",
                "choices": ["json", "csv"],
            },
        },
        "examples": [
            {"name": "Config collector (JSON)", "data": {"collector_type": "config"}},
            {"name": "Job summary (CSV)", "data": {"collector_type": "job_host_summary", "output_format": "csv"}},
            {
                "name": "Anonymized with dates",
                "data": {
                    "collector_type": "anonymized_rollups",
                    "since": EXAMPLE_START_DATE,
                    "until": "2024-01-02T00:00:00Z",
                },
            },
        ],
    },
    "collect_metrics": {
        "category": "Controller metrics",
        "description": "Unified task to collect metrics from multiple collectors",
        "parameters": {
            "database": {"type": "string", "description": LABEL_DB_CONNECTION},
            "since": {"type": "string", "description": LABEL_START_DATE, "pattern": "datetime"},
            "until": {"type": "string", "description": LABEL_END_DATE, "pattern": "datetime"},
            "salt": {"type": "string", "default": "default-salt", "description": DESC_SALT_ANONYMIZATION},
            "collectors": {
                "type": "array",
                "default": ["anonymized_rollups", "config", "job_host_summary", "main_host", "main_jobevent"],
                "description": "List of specific collectors to run",
                "items": ["anonymized_rollups", "config", "job_host_summary", "main_host", "main_jobevent"],
            },
        },
        "examples": [
            {"name": "All collectors (default)", "data": {}},
            {"name": "Specific collectors", "data": {"collectors": ["config", "job_host_summary"]}},
            {
                "name": "Date range with salt",
                "data": {
                    "since": EXAMPLE_START_DATE,
                    "until": "2024-01-02T00:00:00Z",
                    "salt": "custom-salt-value",
                },
            },
        ],
    },
    "anonymize_data": {
        "category": "Controller metrics",
        "description": "Dedicated task to anonymize collected metrics data",
        "parameters": {
            "data": {"type": "object", "required": True, "description": "Raw metrics data to anonymize"},
            "salt": {"type": "string", "description": DESC_SALT_ANONYMIZATION},
            "output_format": {
                "type": "string",
                "default": "segment_ready",
                "description": "Output format for anonymized data",
            },
        },
        "examples": [
            {"name": "Basic anonymization", "data": {"data": {"collectors_run": ["config"], "collected_data": {}}}},
            {"name": "Custom salt", "data": {"data": {"collectors_run": ["config"]}, "salt": "custom-salt"}},
        ],
    },
    "send_to_segment": {
        "category": "Controller metrics",
        "description": "Dedicated task to send anonymized data to Segment.com",
        "parameters": {
            "data": {"type": "object", "required": True, "description": "Anonymized data to send"},
            "user_id": {"type": "string", "default": "anonymous-user", "description": DESC_USER_ID_TRACKING},
            "event_name": {"type": "string", "default": "metrics_sent", "description": DESC_EVENT_NAME_TRACKING},
        },
        "examples": [
            {"name": "Send data", "data": {"data": {"collectors_run": ["config"]}}},
            {"name": "Custom event", "data": {"data": {"collectors_run": []}, "event_name": "custom_metrics"}},
        ],
    },
    "full_process": {
        "category": "Controller metrics",
        "description": "Complete pipeline: collect, anonymize, and send metrics data to Segment.com as single message",
        "parameters": {
            "database": {"type": "string", "description": LABEL_DB_CONNECTION},
            "since": {"type": "string", "description": LABEL_START_DATE, "pattern": "datetime"},
            "until": {"type": "string", "description": LABEL_END_DATE, "pattern": "datetime"},
            "collectors": {
                "type": "array",
                "default": ["anonymized_rollups", "config", "job_host_summary"],
                "description": "List of specific collectors to run",
                "items": ["anonymized_rollups", "config", "job_host_summary", "main_host", "main_jobevent"],
            },
            "salt": {"type": "string", "description": DESC_SALT_ANONYMIZATION},
            "segment_write_key": {
                "type": "string",
                "default": "NA",
                "description": DESC_SEGMENT_WRITE_KEY,
                "sensitive": True,
            },
            "user_id": {"type": "string", "default": "anonymous-user", "description": DESC_USER_ID_TRACKING},
            "event_name": {"type": "string", "default": "metrics_collected", "description": DESC_EVENT_NAME_TRACKING},
            "send_to_segment": {
                "type": "boolean",
                "default": True,
                "description": "Whether to send data to Segment.com",
            },
        },
        "examples": [
            {"name": "Full process", "data": {}},
            {"name": "Custom collectors", "data": {"collectors": ["config", "job_host_summary"]}},
            {"name": "Test mode (no Segment)", "data": {"send_to_segment": False}},
        ],
    },
    "full_process_anonymize": {
        "category": "Controller metrics",
        "description": "Focused pipeline: collect anonymized metrics and send directly to Segment.com as single message",
        "parameters": {
            "database": {"type": "string", "description": LABEL_DB_CONNECTION},
            "since": {"type": "string", "description": LABEL_START_DATE, "pattern": "datetime"},
            "until": {"type": "string", "description": LABEL_END_DATE, "pattern": "datetime"},
            "salt": {"type": "string", "description": DESC_SALT_ANONYMIZATION},
            "segment_write_key": {
                "type": "string",
                "default": "NA",
                "description": DESC_SEGMENT_WRITE_KEY,
                "sensitive": True,
            },
            "user_id": {"type": "string", "default": "anonymous-user", "description": DESC_USER_ID_TRACKING},
            "event_name": {
                "type": "string",
                "default": "anonymized_metrics_collected",
                "description": DESC_EVENT_NAME_TRACKING,
            },
            "send_to_segment": {
                "type": "boolean",
                "default": True,
                "description": "Whether to send data to Segment.com",
            },
        },
        "examples": [
            {"name": "Anonymized collection", "data": {}},
            {"name": "Custom date range", "data": {"since": EXAMPLE_START_DATE, "until": "2024-01-02T00:00:00Z"}},
            {"name": "Test mode (no Segment)", "data": {"send_to_segment": False}},
        ],
    },
}

# Explicit exports for better IDE support
__all__ = [
    # System tasks
    "hello_world",
    "cleanup_old_tasks",
    "execute_db_task",
    "submit_task_to_dispatcher",
    "create_system_tasks",
    "get_system_task_info",
    # Metrics Collection tasks
    "collect_single_collector",
    "collect_metrics",
    "anonymize_data",
    "send_to_segment_task",
    "full_process",
    "full_process_anonymize",
    "METRICS_UTILITY_AVAILABLE",
    # Configuration
    "TASK_FUNCTIONS",
    "TASK_METADATA",
]
