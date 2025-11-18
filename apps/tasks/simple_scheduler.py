"""
Simple task scheduler that manages database tasks and submits them to dispatcherd.

This replaces the complex cron_scheduler with a simpler approach that:
1. Reads tasks from the database
2. Handles both one-time scheduled tasks and recurring tasks
3. Submits tasks to dispatcherd when their time comes
4. Creates system tasks on startup based on feature enables
"""

import threading
import time
from datetime import datetime

from croniter import croniter
from django.conf import settings
from django.utils import timezone

from metrics_service.logger import get_logger

logger = get_logger(__name__)


class SimpleTaskScheduler:
    """Simple scheduler that manages tasks from the database."""

    def __init__(self):
        self.running = False
        self.thread = None
        self.check_interval = 30  # Check every 30 seconds

    def start(self):
        """Start the scheduler."""
        if self.running:
            logger.warning("Scheduler is already running")
            return

        self.running = True
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()
        logger.info("Simple task scheduler started")

    def stop(self):
        """Stop the scheduler."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
        logger.info("Simple task scheduler stopped")

    def _run_loop(self):
        """Main scheduler loop."""
        while self.running:
            try:
                self._check_and_submit_tasks()
                time.sleep(self.check_interval)
            except Exception as e:
                logger.error(f"Error in scheduler loop: {e}")
                time.sleep(self.check_interval)

    def _check_and_submit_tasks(self):
        """Check for tasks that need to be submitted to dispatcherd."""
        try:
            from .models import Task

            now = timezone.now()

            # Get scheduled tasks that are ready to run
            scheduled_tasks = Task.objects.filter(
                status="pending", scheduled_time__lte=now, scheduled_time__isnull=False, is_recurring=False
            )

            for task in scheduled_tasks:
                self._submit_task_to_dispatcherd(task)

            # Handle recurring tasks
            recurring_tasks = Task.objects.filter(
                status="pending", is_recurring=True, cron_expression__isnull=False
            ).exclude(cron_expression="")

            for task in recurring_tasks:
                if self._should_run_recurring_task(task, now):
                    self._submit_task_to_dispatcherd(task)

        except Exception as e:
            logger.error(f"Error checking tasks: {e}")

    def _should_run_recurring_task(self, task, now):
        """Check if a recurring task should run now."""
        try:
            # Use modified time as the last run time, or created time if never modified
            last_run = task.modified or task.created
            if hasattr(last_run, "replace"):
                last_run = last_run.replace(tzinfo=None)

            # Calculate next run time from last run
            cron = croniter(task.cron_expression, last_run)
            next_run = cron.get_next(datetime)

            # Check if it's time to run (within check interval)
            current_time = now.replace(tzinfo=None) if hasattr(now, "replace") else now
            time_diff = (next_run - current_time).total_seconds()

            # Run if we're past the scheduled time (negative time_diff means overdue)
            return time_diff <= 0

        except Exception as e:
            logger.error(f"Error checking recurring task {task.id}: {e}")
            return False

    def _submit_task_to_dispatcherd(self, task):
        """Submit a task to dispatcherd."""
        try:
            from .tasks import submit_task_to_dispatcher

            logger.info(f"Submitting task {task.name} (ID: {task.id}) to dispatcherd")
            submit_task_to_dispatcher(task)

            # For recurring tasks, update the last run time
            if task.is_recurring and task.cron_expression:
                self._update_recurring_task_last_run(task)

        except Exception as e:
            logger.error(f"Error submitting task {task.id}: {e}")
            task.status = "failed"
            task.error_message = f"Failed to submit to dispatcher: {str(e)}"
            task.save()

    def _update_recurring_task_last_run(self, task):
        """Update the last run time for a recurring task."""
        try:
            # Just update the modified timestamp by saving the task
            # This will be used as the "last run" time for calculating next run
            task._skip_signals = True  # Prevent signals from firing
            task.save(update_fields=["modified"])

            logger.info(f"Updated last run time for recurring task: {task.name}")

        except Exception as e:
            logger.error(f"Error updating last run time for task {task.id}: {e}")


def initialize_system_tasks():
    """Initialize system tasks based on feature enables."""
    try:
        from django.contrib.auth import get_user_model

        from .models import Task

        user_model = get_user_model()

        # Get or create a system user
        system_user, _ = user_model.objects.get_or_create(username="system", defaults={"email": "system@localhost"})

        system_tasks = []

        # Check feature enables and add appropriate system tasks
        feature_enabled = getattr(settings, "FEATURE_ENABLED", {})

        # Metrics collection system task
        if feature_enabled.get("METRICS_COLLECTION_ENABLED", True):
            system_tasks.append(
                {
                    "name": "Metrics Collection",
                    "function_name": "process_user_data",
                    "cron_expression": "0 2 * * *",  # Daily at 2 AM
                    "task_data": {"operation": "metrics_collection"},
                    "is_recurring": True,
                    "is_system_task": True,
                    "priority": 1,
                }
            )

        # Anonymized data cleanup task
        if feature_enabled.get("ANONYMIZED_DATA_ENABLED", True):
            system_tasks.append(
                {
                    "name": "Anonymized Data Cleanup",
                    "function_name": "cleanup_old_data",
                    "cron_expression": "0 3 * * 0",  # Weekly on Sunday at 3 AM
                    "task_data": {"days_old": 90, "anonymize": True},
                    "is_recurring": True,
                    "is_system_task": True,
                    "priority": 2,
                }
            )

        # General cleanup task (always enabled)
        system_tasks.append(
            {
                "name": "System Cleanup",
                "function_name": "cleanup_old_data",
                "cron_expression": "0 1 * * *",  # Daily at 1 AM
                "task_data": {"days_old": 30},
                "is_recurring": True,
                "is_system_task": True,
                "priority": 3,
            }
        )

        created_count = 0
        for task_config in system_tasks:
            # Check if this system task already exists
            existing = Task.objects.filter(name=task_config["name"], is_system_task=True).first()

            if not existing:
                Task.objects.create(created_by=system_user, **task_config)
                created_count += 1
                logger.info(f"Created system task: {task_config['name']}")

        if created_count > 0:
            logger.info(f"Initialized {created_count} system tasks")
        else:
            logger.debug("All system tasks already exist")

    except Exception as e:
        logger.error(f"Error initializing system tasks: {e}")


# Global scheduler instance
_scheduler = None


def start_scheduler():
    """Start the global scheduler instance."""
    global _scheduler
    if _scheduler is None:
        _scheduler = SimpleTaskScheduler()
    _scheduler.start()


def stop_scheduler():
    """Stop the global scheduler instance."""
    global _scheduler
    if _scheduler:
        _scheduler.stop()


def get_scheduler():
    """Get the global scheduler instance."""
    global _scheduler
    if _scheduler is None:
        _scheduler = SimpleTaskScheduler()
    return _scheduler


def refresh_scheduler():
    """Signal the scheduler to refresh its task list (for API/dashboard updates)."""
    # The scheduler automatically picks up new tasks on its next check cycle
    logger.info("Scheduler refresh requested - will pick up new tasks on next cycle")
