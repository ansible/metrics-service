"""
Cron-based task scheduler using APScheduler.

This module provides a dictionary-based task scheduler that replaces the
database polling approach with a more efficient cron-based system.
"""

import logging
import threading
from typing import Any

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from django.utils import timezone

from .task_groups import get_all_enabled_tasks, get_task_group_status
from .tasks import TASK_FUNCTIONS

logger = logging.getLogger(__name__)


class CronTaskScheduler:
    """
    Cron-based task scheduler using APScheduler.

    This scheduler uses a dictionary-based approach instead of polling
    the database, providing better performance and immediate task execution.
    """

    def __init__(self):
        """Initialize the cron scheduler."""
        self.scheduler = BackgroundScheduler()
        self.running = False
        self._lock = threading.Lock()

        # Task registry for scheduled tasks
        # Tasks are now loaded from task groups with feature flag control
        self.task_registry: dict[str, dict[str, Any]] = {}
        self._load_task_registry()

    def _load_task_registry(self):
        """Load task registry from task groups with feature flag control."""
        try:
            enabled_tasks = get_all_enabled_tasks()
            self.task_registry = enabled_tasks
            logger.info(f"Loaded {len(enabled_tasks)} enabled tasks from task groups")

            # Log which groups are enabled/disabled
            group_status = get_task_group_status()
            for group_name, status in group_status.items():
                if status["enabled"]:
                    logger.info(
                        f"Task group '{group_name}' enabled: {status['enabled_tasks']}/{status['total_tasks']} tasks"
                    )
                else:
                    logger.info(f"Task group '{group_name}' disabled: {status['total_tasks']} tasks skipped")

        except Exception as e:
            logger.error(f"Failed to load task registry from groups: {str(e)}")
            # Fallback to empty registry
            self.task_registry = {}

    def reload_task_registry(self):
        """Reload task registry from task groups (useful when feature flags change)."""
        logger.info("Reloading task registry from task groups")
        old_count = len(self.task_registry)

        # Stop existing tasks
        if self.running:
            for task_id in list(self.task_registry.keys()):
                try:
                    self.scheduler.remove_job(task_id)
                except Exception as e:
                    logger.debug(f"Job {task_id} not found in scheduler: {str(e)}")

        # Reload registry
        self._load_task_registry()

        # Re-add tasks if scheduler is running
        if self.running:
            self._add_registry_tasks()

        new_count = len(self.task_registry)
        logger.info(f"Task registry reloaded: {old_count} -> {new_count} tasks")

    def start(self):
        """Start the cron scheduler."""
        with self._lock:
            if self.running:
                logger.warning("Scheduler is already running")
                return

            try:
                # Add all enabled tasks to the scheduler
                self._add_registry_tasks()

                # Start the scheduler
                self.scheduler.start()
                self.running = True

                logger.info("Cron-based task scheduler started")
                logger.info(f"Registered {len(self.task_registry)} scheduled tasks")

            except Exception as e:
                logger.error(f"Failed to start cron scheduler: {str(e)}")
                raise

    def stop(self):
        """Stop the cron scheduler."""
        with self._lock:
            if not self.running:
                return

            try:
                self.scheduler.shutdown()
                self.running = False
                logger.info("Cron-based task scheduler stopped")
            except Exception as e:
                logger.error(f"Error stopping cron scheduler: {str(e)}")

    def _add_registry_tasks(self):
        """Add all enabled tasks from the registry to the scheduler."""
        for task_id, config in self.task_registry.items():
            if not config.get("enabled", True):
                logger.debug(f"Skipping disabled task: {task_id}")
                continue

            try:
                self._add_scheduled_task(task_id, config)
            except Exception as e:
                logger.error(f"Failed to add task {task_id}: {str(e)}")

    def _add_scheduled_task(self, task_id: str, config: dict[str, Any]):
        """Add a single scheduled task to the scheduler."""
        function_name = config["function"]

        # Validate function exists
        if function_name not in TASK_FUNCTIONS:
            raise ValueError(f"Unknown task function: {function_name}")

        # Create trigger based on cron expression
        trigger = CronTrigger.from_crontab(config["cron"])

        # Add job to scheduler
        self.scheduler.add_job(
            func=self._execute_scheduled_task,
            trigger=trigger,
            args=[task_id, function_name, config.get("args", {})],
            id=task_id,
            name=config.get("description", task_id),
            replace_existing=True,
            max_instances=1,  # Prevent overlapping executions
        )

        logger.info(f"Added scheduled task: {task_id} ({config['cron']})")

    def _execute_scheduled_task(self, task_id: str, function_name: str, args: dict[str, Any]):
        """Execute a scheduled task by submitting it to dispatcherd."""
        try:
            # Ensure dispatcherd is configured before attempting to submit tasks
            from .dispatcherd_config import ensure_dispatcherd_configured

            ensure_dispatcherd_configured()

            from dispatcherd.publish import submit_task

            # Validate the task function exists
            if function_name not in TASK_FUNCTIONS:
                raise ValueError(f"Unknown task function: {function_name}")

            # Determine queue based on function name
            queue = self._get_queue_for_function(function_name)

            # Submit to dispatcherd using function object directly
            task_func = TASK_FUNCTIONS[function_name]
            submit_task(task_func, kwargs=args, queue=queue)

            logger.info(f"Submitted scheduled task {task_id} ({function_name}) to queue {queue}")

        except Exception as e:
            logger.error(f"Failed to execute scheduled task {task_id}: {str(e)}")

    def _get_queue_for_function(self, function_name: str) -> str:
        """Determine the appropriate queue for a function."""
        queue_mapping = {
            "hello_world": "metrics_tasks",
            "cleanup_old_data": "metrics_cleanup",
            "cleanup_old_tasks": "metrics_cleanup",
            "send_notification_email": "metrics_notifications",
            "process_user_data": "metrics_tasks",
            "execute_db_task": "metrics_tasks",
            "sleep": "metrics_tasks",
            # Metrics collection tasks
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

    def add_dynamic_task(
        self,
        task_id: str,
        function_name: str,
        cron_expression: str,
        args: dict[str, Any] = None,
        description: str = None,
    ):
        """
        Add a dynamic task to the scheduler.

        Args:
            task_id: Unique identifier for the task
            function_name: Name of the function to execute
            cron_expression: Cron expression for scheduling
            args: Arguments to pass to the function
            description: Human-readable description
        """
        if args is None:
            args = {}

        config = {
            "function": function_name,
            "cron": cron_expression,
            "args": args,
            "enabled": True,
            "description": description or task_id,
        }

        try:
            self._add_scheduled_task(task_id, config)
            self.task_registry[task_id] = config
            logger.info(f"Added dynamic task: {task_id}")
        except Exception as e:
            logger.error(f"Failed to add dynamic task {task_id}: {str(e)}")
            raise

    def remove_task(self, task_id: str):
        """Remove a task from the scheduler."""
        try:
            self.scheduler.remove_job(task_id)
            if task_id in self.task_registry:
                del self.task_registry[task_id]
            logger.info(f"Removed task: {task_id}")
        except Exception as e:
            logger.error(f"Failed to remove task {task_id}: {str(e)}")

    def update_task(self, task_id: str, **kwargs):
        """Update an existing task's configuration."""
        if task_id not in self.task_registry:
            raise ValueError(f"Task {task_id} not found")

        # Update registry
        self.task_registry[task_id].update(kwargs)

        # Remove and re-add to scheduler
        self.scheduler.remove_job(task_id)
        self._add_scheduled_task(task_id, self.task_registry[task_id])

        logger.info(f"Updated task: {task_id}")

    def get_task_status(self, task_id: str) -> dict[str, Any] | None:
        """Get the status of a scheduled task."""
        try:
            job = self.scheduler.get_job(task_id)
            if job:
                return {"id": job.id, "name": job.name, "next_run_time": job.next_run_time, "trigger": str(job.trigger)}
        except Exception as e:
            logger.error(f"Failed to get status for task {task_id}: {str(e)}")
        return None

    def list_tasks(self) -> dict[str, Any]:
        """List all registered tasks."""
        return {
            "registry": self.task_registry,
            "scheduled_jobs": [
                {"id": job.id, "name": job.name, "next_run_time": job.next_run_time, "trigger": str(job.trigger)}
                for job in self.scheduler.get_jobs()
            ],
            "task_groups": get_task_group_status(),
        }

    def get_task_groups_info(self) -> dict[str, Any]:
        """Get detailed information about task groups and their status."""
        return get_task_group_status()

    def schedule_immediate_task(self, function_name: str, args: dict[str, Any] = None, queue: str = None) -> str:
        """
        Schedule a task to run immediately.

        Args:
            function_name: Name of the function to execute
            args: Arguments to pass to the function
            queue: Queue to submit to (optional)

        Returns:
            Job ID for the scheduled task
        """
        if args is None:
            args = {}

        if queue is None:
            queue = self._get_queue_for_function(function_name)

        job_id = f"immediate_{timezone.now().timestamp()}"

        try:
            # Ensure dispatcherd is configured before attempting to submit tasks
            from .dispatcherd_config import ensure_dispatcherd_configured

            ensure_dispatcherd_configured()

            from dispatcherd.publish import submit_task

            # Validate the task function exists
            if function_name not in TASK_FUNCTIONS:
                raise ValueError(f"Unknown task function: {function_name}")

            # Submit immediately using string reference
            submit_task(f"apps.tasks.tasks.{function_name}", kwargs=args, queue=queue)

            logger.info(f"Scheduled immediate task {job_id} ({function_name}) to queue {queue}")
            return job_id

        except Exception as e:
            logger.error(f"Failed to schedule immediate task {function_name}: {str(e)}")
            raise


# Global scheduler instance
_scheduler_instance: CronTaskScheduler | None = None


def get_scheduler() -> CronTaskScheduler:
    """Get the global scheduler instance."""
    global _scheduler_instance
    if _scheduler_instance is None:
        _scheduler_instance = CronTaskScheduler()
    return _scheduler_instance


def start_scheduler():
    """Start the global scheduler."""
    scheduler = get_scheduler()
    scheduler.start()
    return scheduler


def stop_scheduler():
    """Stop the global scheduler."""
    global _scheduler_instance
    if _scheduler_instance:
        _scheduler_instance.stop()
        _scheduler_instance = None
