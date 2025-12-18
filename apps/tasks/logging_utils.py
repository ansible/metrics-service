"""
Centralized logging utilities for task management.

This module provides standardized logging patterns for all task-related operations,
reducing code duplication and ensuring consistent log formatting across the codebase.
"""

import logging

logger = logging.getLogger(__name__)


class TaskLogger:
    """
    Centralized logging class for task operations.

    Provides standardized logging methods with consistent formatting for all
    task-related operations. This eliminates repeated logging patterns across
    tasks_system.py, tasks_collector.py, cron_scheduler.py, and utils.py.

    Usage:
        task_logger = TaskLogger("my_task")
        task_logger.log_start("Beginning task execution")
        task_logger.log_progress("Processing", "Processed 10 items")
        task_logger.log_complete("Task finished successfully")

    Format:
        [TASK:{task_name}] {operation}: {details}
    """

    def __init__(self, task_name: str):
        """
        Initialize TaskLogger for a specific task.

        Args:
            task_name: Name of the task for logging context
        """
        self.task_name = task_name
        self.logger = logging.getLogger(f"apps.tasks.{task_name}")

    def _format_message(self, operation: str, details: str = "") -> str:
        """
        Format a log message with standard structure.

        Args:
            operation: Operation being performed
            details: Additional context

        Returns:
            Formatted log message
        """
        base_msg = f"[TASK:{self.task_name}] {operation}"
        if details:
            return f"{base_msg}: {details}"
        return base_msg

    def log_start(self, details: str = "") -> None:
        """
        Log task start.

        Args:
            details: Additional context about task start
        """
        message = self._format_message("START", details or f"Starting {self.task_name}")
        self.logger.info(message)

    def log_progress(self, operation: str, details: str = "") -> None:
        """
        Log task progress during execution.

        Args:
            operation: Current operation being performed
            details: Additional context about the operation
        """
        message = self._format_message(operation, details)
        self.logger.info(message)

    def log_complete(self, details: str = "") -> None:
        """
        Log task completion.

        Args:
            details: Additional context about completion
        """
        message = self._format_message("COMPLETE", details or f"{self.task_name} completed successfully")
        self.logger.info(message)

    def log_error(self, error: Exception | str, exc_info: bool = False) -> None:
        """
        Log task error.

        Args:
            error: Error that occurred (Exception or error message string)
            exc_info: Whether to include exception traceback
        """
        error_str = str(error)
        message = self._format_message("ERROR", error_str)
        self.logger.error(message, exc_info=exc_info)

    def log_warning(self, warning: str) -> None:
        """
        Log task warning.

        Args:
            warning: Warning message
        """
        message = self._format_message("WARNING", warning)
        self.logger.warning(message)

    def log_submission(self, queue: str, task_id: int | None = None) -> None:
        """
        Log task submission to dispatcher queue.

        Args:
            queue: Name of the queue task was submitted to
            task_id: Optional task ID for reference
        """
        id_info = f" (ID: {task_id})" if task_id else ""
        message = self._format_message("SUBMITTED", f"to queue '{queue}'{id_info}")
        self.logger.info(message)

    def log_debug(self, details: str) -> None:
        """
        Log debug information.

        Args:
            details: Debug information
        """
        message = self._format_message("DEBUG", details)
        self.logger.debug(message)


def get_task_logger(task_name: str) -> TaskLogger:
    """
    Factory function to create a TaskLogger instance.

    This provides a convenient way to create task loggers without
    directly instantiating the class.

    Args:
        task_name: Name of the task for logging context

    Returns:
        TaskLogger instance for the specified task
    """
    return TaskLogger(task_name)


# Backward compatibility: expose the existing log_task_execution pattern
def log_task_execution(task_name: str, operation: str, details: str = "", level: str = "info") -> None:
    """
    Standardized logging for task execution.

    This function maintains backward compatibility with the existing log_task_execution
    pattern while delegating to the TaskLogger class for consistency.

    Args:
        task_name: Name of the task
        operation: Operation being performed (start, complete, error, etc.)
        details: Additional details to log
        level: Log level (info, warning, error, debug)
    """
    task_logger = TaskLogger(task_name)

    level_mapping = {
        "info": task_logger.log_progress,
        "error": task_logger.log_error,
        "warning": task_logger.log_warning,
        "debug": task_logger.log_debug,
    }

    # Special handling for common operations
    if operation.lower() == "start":
        task_logger.log_start(details)
    elif operation.lower() in ("complete", "completed", "success"):
        task_logger.log_complete(details)
    else:
        # Use appropriate level or default to progress
        log_func = level_mapping.get(level.lower(), task_logger.log_progress)
        if level.lower() == "error":
            log_func(details if details else operation)
        else:
            log_func(operation, details)
