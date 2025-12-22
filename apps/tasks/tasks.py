"""
Background tasks for metrics_service using dispatcherd.

This module serves as an aggregator, importing and re-exporting tasks from
specialized modules for backward compatibility:
- tasks_system: System maintenance, cleanup, and communication tasks
- tasks_collector: Metrics collection and anonymized data collection tasks
"""

import logging

# Import all collector tasks
from .tasks_collector import (
    METRICS_UTILITY_AVAILABLE,
    anonymize_data,
    collect_all_metrics,
    collect_anonymous_metrics,
    collect_config_metrics,
    collect_host_metrics,
    collect_host_metrics_hourly,
    collect_job_host_summary,
    collect_job_host_summary_hourly,
    collect_main_host_hourly,
    collect_metrics,
    daily_anonymize_and_prepare,
    daily_metrics_rollup,
    full_process,
    full_process_anonymize,
    send_anonymized_to_segment,
    send_to_segment_task,
)

# Import all system tasks
from .tasks_system import (
    SYSTEM_TASKS,
    cleanup_metrics_data,
    cleanup_old_data,
    cleanup_old_tasks,
    create_system_tasks,
    execute_db_task,
    get_system_task_info,
    hello_world,
    process_user_data,
    send_notification_email,
    sleep,
    submit_task_to_dispatcher,
)

logger = logging.getLogger(__name__)

# Constants for repeated strings (used in TASK_METADATA)
MSG_METRICS_UTILITY_NOT_AVAILABLE = "metrics-utility is not available"
LABEL_METRICS_COLLECTION = "Metrics Collection"
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
    "cleanup_old_data": cleanup_old_data,
    "cleanup_old_tasks": cleanup_old_tasks,
    "cleanup_metrics_data": cleanup_metrics_data,
    "send_notification_email": send_notification_email,
    "process_user_data": process_user_data,
    "execute_db_task": execute_db_task,
    "sleep": sleep,
    # Hourly Metrics Collection Tasks
    "collect_job_host_summary_hourly": collect_job_host_summary_hourly,
    "collect_host_metrics_hourly": collect_host_metrics_hourly,
    "collect_main_host_hourly": collect_main_host_hourly,
    # Daily Rollup and Anonymization Tasks
    "daily_metrics_rollup": daily_metrics_rollup,
    "daily_anonymize_and_prepare": daily_anonymize_and_prepare,
    "send_anonymized_to_segment": send_anonymized_to_segment,
    # Metrics Collection Tasks (unified + individual collectors)
    "collect_metrics": collect_metrics,
    "collect_all_metrics": collect_all_metrics,
    "collect_anonymous_metrics": collect_anonymous_metrics,
    "collect_config_metrics": collect_config_metrics,
    "collect_job_host_summary": collect_job_host_summary,
    "collect_host_metrics": collect_host_metrics,
    "anonymize_data": anonymize_data,
    "send_to_segment": send_to_segment_task,
    "full_process": full_process,
    "full_process_anonymize": full_process_anonymize,
}

# Enhanced task metadata for dashboard display
TASK_METADATA = {
    "hello_world": {
        "category": "Testing",
        "description": "Simple hello world task for testing the dispatcherd integration",
        "parameters": {},
        "examples": [{"name": "Basic Hello World", "data": {}}],
    },
    "sleep": {
        "category": "Testing",
        "description": "Sleep for a specified number of seconds (useful for testing)",
        "parameters": {
            "duration": {
                "type": "integer",
                "default": 10,
                "description": "Number of seconds to sleep",
                "min": 1,
                "max": 300,
            }
        },
        "examples": [
            {"name": "Sleep 10 seconds", "data": {"duration": 10}},
            {"name": "Sleep 30 seconds", "data": {"duration": 30}},
        ],
    },
    "cleanup_old_data": {
        "category": "Maintenance",
        "description": "Clean up old data from the system based on age criteria",
        "parameters": {
            "days_old": {
                "type": "integer",
                "default": 30,
                "description": "Number of days old data should be to qualify for cleanup",
                "min": 1,
                "max": 365,
            },
            "data_types": {
                "type": "array",
                "default": ["default"],
                "description": "List of data types to clean up",
                "items": ["logs", "temp_files", "cache", "default"],
            },
        },
        "examples": [
            {"name": "Cleanup 30 day old data", "data": {"days_old": 30}},
            {"name": "Cleanup logs older than 7 days", "data": {"days_old": 7, "data_types": ["logs"]}},
        ],
    },
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
    "send_notification_email": {
        "category": "Communication",
        "description": "Send notification email to specified recipients",
        "parameters": {
            "recipient": {
                "type": "string",
                "required": True,
                "description": "Email address of the recipient",
                "pattern": "email",
            },
            "subject": {"type": "string", "default": "Notification", "description": "Email subject line"},
            "message": {"type": "string", "default": "", "description": "Email message body"},
            "html_message": {"type": "string", "description": "Optional HTML version of the message"},
        },
        "examples": [
            {
                "name": "Basic notification",
                "data": {
                    "recipient": "admin@example.com",
                    "subject": "System Alert",
                    "message": "System maintenance completed",
                },
            },
            {
                "name": "Custom message",
                "data": {"recipient": "user@example.com", "subject": "Welcome", "message": "Welcome to our service!"},
            },
        ],
    },
    "process_user_data": {
        "category": "Data Processing",
        "description": "Process user data in the background with various operations",
        "parameters": {
            "user_id": {"type": "integer", "description": "ID of the user to process (required for most operations)"},
            "operation": {
                "type": "string",
                "default": "sync",
                "description": "Type of operation to perform",
                "choices": ["sync", "validate", "hello_world"],
            },
            "message": {"type": "string", "description": "Custom message for hello_world operation"},
        },
        "examples": [
            {"name": "Hello World", "data": {"operation": "hello_world", "message": "Hello from the system!"}},
            {"name": "Sync user data", "data": {"user_id": 1, "operation": "sync"}},
            {"name": "Validate user", "data": {"user_id": 1, "operation": "validate"}},
        ],
    },
    "execute_db_task": {
        "category": "System",
        "description": "Execute a database-defined task with comprehensive lifecycle management",
        "parameters": {
            "task_id": {"type": "integer", "required": True, "description": "ID of the task to execute"},
            "execution_id": {"type": "integer", "description": "ID of the execution record (optional)"},
        },
        "examples": [{"name": "Execute task by ID", "data": {"task_id": 123}}],
    },
    "collect_metrics": {
        "category": LABEL_METRICS_COLLECTION,
        "description": "Unified task to collect metrics from all available collectors",
        "parameters": {
            "database": {"type": "string", "description": LABEL_DB_CONNECTION},
            "since": {"type": "string", "description": LABEL_START_DATE, "pattern": "datetime"},
            "until": {"type": "string", "description": LABEL_END_DATE, "pattern": "datetime"},
            "collectors": {
                "type": "array",
                "default": ["anonymized_rollups", "config", "job_host_summary", "main_host", "main_jobevent"],
                "description": "List of specific collectors to run",
                "items": ["anonymized_rollups", "config", "job_host_summary", "main_host", "main_jobevent"],
            },
        },
        "examples": [
            {"name": "All collectors", "data": {}},
            {"name": "Specific collectors", "data": {"collectors": ["config", "job_host_summary"]}},
            {"name": "Date range collection", "data": {"since": EXAMPLE_START_DATE, "until": "2024-01-02T00:00:00Z"}},
        ],
    },
    "anonymize_data": {
        "category": LABEL_METRICS_COLLECTION,
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
        "category": LABEL_METRICS_COLLECTION,
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
        "category": LABEL_METRICS_COLLECTION,
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
        "category": LABEL_METRICS_COLLECTION,
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
    "sleep",
    "cleanup_old_data",
    "cleanup_old_tasks",
    "send_notification_email",
    "process_user_data",
    "execute_db_task",
    "submit_task_to_dispatcher",
    "create_system_tasks",
    "get_system_task_info",
    "SYSTEM_TASKS",
    # Metrics Collection tasks
    "collect_metrics",
    "collect_all_metrics",
    "collect_anonymous_metrics",
    "collect_config_metrics",
    "collect_host_metrics",
    "collect_job_host_summary",
    "anonymize_data",
    "send_to_segment_task",
    "full_process",
    "full_process_anonymize",
    "METRICS_UTILITY_AVAILABLE",
    # Configuration
    "TASK_FUNCTIONS",
    "TASK_METADATA",
]
