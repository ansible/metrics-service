"""
Task scheduler using APScheduler.

This module provides a task scheduler that handles both task group definitions
and database tasks without database polling, using APScheduler for optimal performance.
"""

import logging
import threading
from typing import Any

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from django.utils import timezone

from .task_groups import get_all_enabled_tasks, get_task_group_status
from .tasks import TASK_FUNCTIONS

logger = logging.getLogger(__name__)


class UnifiedTaskScheduler:
    """
    Task scheduler using APScheduler.

    This scheduler handles both task group definitions and database tasks
    without database polling, providing optimal performance for all task types.
    """

    def __init__(self, check_interval: int = 60):
        """Initialize the task scheduler."""
        self.scheduler = BackgroundScheduler()
        self.running = False
        self._lock = threading.Lock()
        self.check_interval = check_interval

        # Task registry for scheduled tasks from task groups
        self.task_registry: dict[str, dict[str, Any]] = {}
        self._load_task_registry()

        # Database task tracking
        self._db_task_jobs: dict[int, str] = {}  # task_id -> job_id mapping

    def _load_task_registry(self):
        """Load task registry from task groups with feature enable control."""
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
        """Reload task registry from task groups (useful when feature enables change)."""
        logger.info("Reloading task registry from task groups")
        old_count = len(self.task_registry)

        # Stop existing tasks
        if self.running:
            for task_id in self.task_registry:
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

                # Load database tasks into scheduler
                self._sync_database_tasks()

                logger.info("Task scheduler started")
                logger.info(f"Registered {len(self.task_registry)} task group tasks")
                logger.info(f"Loaded {len(self._db_task_jobs)} database tasks")

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
                self._db_task_jobs.clear()
                logger.info("Task scheduler stopped")
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
            from .submission_utils import determine_task_queue

            queue = determine_task_queue(function_name)

            # Submit to dispatcherd using string reference for consistency
            submit_task(f"apps.tasks.tasks.{function_name}", kwargs=args, queue=queue)

            # Log submission using TaskLogger for consistency
            from .logging_utils import TaskLogger

            task_logger = TaskLogger(function_name)
            task_logger.log_submission(queue=queue, task_id=task_id)

        except Exception as e:
            logger.error(f"Failed to execute scheduled task {task_id}: {str(e)}")

    def _get_queue_for_function(self, function_name: str) -> str:
        """
        Determine the appropriate queue for a function.

        DEPRECATED: This method now delegates to submission_utils.determine_task_queue()
        to avoid code duplication. Kept for backward compatibility.
        """
        from .submission_utils import determine_task_queue

        return determine_task_queue(function_name)

    def _sync_database_tasks(self):
        """Synchronize database tasks with the scheduler."""
        try:
            from .models import Task

            # Get all pending database tasks that are scheduled or recurring
            scheduled_tasks = Task.objects.filter(status="pending", scheduled_time__isnull=False, is_recurring=False)

            recurring_tasks = Task.objects.filter(
                status="pending", is_recurring=True, cron_expression__isnull=False
            ).exclude(cron_expression="")

            # Add scheduled tasks
            for task in scheduled_tasks:
                self._add_database_scheduled_task(task)

            # Add recurring tasks
            for task in recurring_tasks:
                self._add_database_recurring_task(task)

            logger.info(
                f"Synchronized {len(scheduled_tasks)} scheduled and {len(recurring_tasks)} recurring database tasks"
            )

        except Exception as e:
            logger.error(f"Error synchronizing database tasks: {e}")

    def _add_database_scheduled_task(self, task):
        """Add a one-time scheduled database task to the scheduler."""
        if task.id in self._db_task_jobs:
            return  # Already scheduled

        try:
            job_id = f"db_task_{task.id}"

            # Create date trigger for the scheduled time
            trigger = DateTrigger(run_date=task.scheduled_time)

            # Add job to scheduler
            self.scheduler.add_job(
                func=self._execute_database_task,
                trigger=trigger,
                args=[task.id],
                id=job_id,
                name=f"DB Task: {task.name}",
                replace_existing=True,
                max_instances=1,
            )

            self._db_task_jobs[task.id] = job_id
            logger.info(f"Added scheduled database task: {task.name} (ID: {task.id}) at {task.scheduled_time}")

        except Exception as e:
            logger.error(f"Failed to add scheduled database task {task.id}: {e}")

    def _add_database_recurring_task(self, task):
        """Add a recurring database task to the scheduler."""
        if task.id in self._db_task_jobs:
            return  # Already scheduled

        try:
            job_id = f"db_recurring_{task.id}"

            # Create cron trigger from expression
            trigger = CronTrigger.from_crontab(task.cron_expression)

            # Add job to scheduler
            self.scheduler.add_job(
                func=self._execute_database_task,
                trigger=trigger,
                args=[task.id],
                id=job_id,
                name=f"DB Recurring: {task.name}",
                replace_existing=True,
                max_instances=1,
            )

            self._db_task_jobs[task.id] = job_id
            logger.info(f"Added recurring database task: {task.name} (ID: {task.id}) with cron: {task.cron_expression}")

        except Exception as e:
            logger.error(f"Failed to add recurring database task {task.id}: {e}")

    def _execute_database_task(self, task_id: int):
        """Execute a database task by submitting it to dispatcherd."""
        try:
            from .models import Task

            # Get the task
            task = Task.objects.get(id=task_id, status="pending")

            logger.info(f"Executing database task: {task.name} (ID: {task_id})")

            # Import submit function here to avoid circular imports
            from .tasks_system import submit_task_to_dispatcher

            # Submit to dispatcherd
            submit_task_to_dispatcher(task)

            # For non-recurring tasks, remove from tracking
            if not task.is_recurring:
                self._remove_database_task(task_id)

        except Task.DoesNotExist:
            logger.warning(f"Database task {task_id} not found or not pending")
            self._remove_database_task(task_id)
        except Exception as e:
            logger.error(f"Failed to execute database task {task_id}: {e}")

    def _remove_database_task(self, task_id: int):
        """Remove a database task from the scheduler."""
        if task_id in self._db_task_jobs:
            job_id = self._db_task_jobs[task_id]
            try:
                self.scheduler.remove_job(job_id)
            except Exception as e:
                logger.debug(f"Job {job_id} not found in scheduler: {e}")
            del self._db_task_jobs[task_id]

    def add_database_task(self, task):
        """Add a database task to the scheduler (called by signals)."""
        if not self.running:
            return

        try:
            if task.scheduled_time and not task.is_recurring:
                self._add_database_scheduled_task(task)
            elif task.is_recurring and task.cron_expression:
                self._add_database_recurring_task(task)

        except Exception as e:
            logger.error(f"Failed to add database task {task.id}: {e}")

    def update_database_task(self, task):
        """Update a database task in the scheduler (called by signals)."""
        if not self.running:
            return

        # Remove existing job
        self._remove_database_task(task.id)

        # Add updated task if still pending and scheduled
        if task.status == "pending":
            self.add_database_task(task)

    def remove_database_task_by_id(self, task_id: int):
        """Remove a database task by ID (called by signals)."""
        self._remove_database_task(task_id)

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
        scheduled_jobs = [
            {"id": job.id, "name": job.name, "next_run_time": job.next_run_time, "trigger": str(job.trigger)}
            for job in self.scheduler.get_jobs()
        ]

        return {
            "task_groups": self.task_registry,
            "database_tasks": len(self._db_task_jobs),
            "scheduled_jobs": scheduled_jobs,
            "task_groups_status": get_task_group_status(),
            "total_jobs": len(scheduled_jobs),
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
_scheduler_instance: UnifiedTaskScheduler | None = None


def get_scheduler() -> UnifiedTaskScheduler:
    """Get the global scheduler instance."""
    global _scheduler_instance
    if _scheduler_instance is None:
        _scheduler_instance = UnifiedTaskScheduler()
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


def sync_database_tasks():
    """Synchronize database tasks with the scheduler."""
    scheduler = get_scheduler()
    if scheduler.running:
        scheduler._sync_database_tasks()


def refresh_scheduler():
    """Refresh the scheduler to pick up new database tasks."""
    scheduler = get_scheduler()
    if scheduler.running:
        scheduler._sync_database_tasks()


# Aliases for backward compatibility
CronTaskScheduler = UnifiedTaskScheduler
