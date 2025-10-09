"""
Cron scheduler management service.

Handles all cron-related operations including starting/stopping the scheduler,
listing tasks, and managing scheduled jobs.
"""

from typing import Any, Dict

from django.core.management.base import CommandError


class CronManager:
    """Manages cron scheduler operations for the metrics service."""

    def __init__(self, output_formatter):
        """
        Initialize the cron manager.

        Args:
            output_formatter: OutputFormatter instance for consistent output
        """
        self.output = output_formatter

    def start_scheduler(self) -> None:
        """Start the cron scheduler."""
        try:
            from apps.tasks.cron_scheduler import start_scheduler

            start_scheduler()
            self.output.success("Cron scheduler started")
        except Exception as e:
            raise CommandError(f"Failed to start cron scheduler: {e}") from e

    def stop_scheduler(self) -> None:
        """Stop the cron scheduler."""
        try:
            from apps.tasks.cron_scheduler import stop_scheduler

            stop_scheduler()
            self.output.success("Cron scheduler stopped")
        except Exception as e:
            raise CommandError(f"Failed to stop cron scheduler: {e}") from e

    def show_status(self) -> None:
        """Show cron scheduler status."""
        try:
            from apps.tasks.cron_scheduler import get_scheduler

            scheduler = get_scheduler()
            if scheduler.running:
                self.output.success("Cron scheduler is running")
            else:
                self.output.warning("Cron scheduler is not running")
        except Exception as e:
            raise CommandError(f"Failed to get cron scheduler status: {e}") from e

    def list_tasks(self) -> None:
        """List cron tasks and scheduled jobs."""
        try:
            from apps.tasks.cron_scheduler import get_scheduler

            scheduler = get_scheduler()
            task_info = scheduler.list_tasks()

            registry = task_info.get("registry", {})
            scheduled_jobs = task_info.get("scheduled_jobs", [])

            self._display_task_registry(registry)
            self._display_scheduled_jobs(scheduled_jobs)

        except Exception as e:
            raise CommandError(f"Failed to list cron tasks: {e}") from e

    def _display_task_registry(self, registry: Dict[str, Any]) -> None:
        """Display the task registry."""
        self.output.write(f"Task Registry ({len(registry)} tasks):")
        self.output.write_separator("-", 50)

        for task_id, config in registry.items():
            enabled = "✓" if config.get("enabled", True) else "✗"
            self.output.write(f"{enabled} {task_id}")
            self.output.write(f"  Function: {config['function']}")
            self.output.write(f"  Schedule: {config['cron']}")
            self.output.write(f"  Description: {config.get('description', 'N/A')}")
            self.output.write("")

    def _display_scheduled_jobs(self, scheduled_jobs: list) -> None:
        """Display scheduled jobs."""
        if scheduled_jobs:
            self.output.write(f"Scheduled Jobs ({len(scheduled_jobs)}):")
            self.output.write_separator("-", 50)

            for job in scheduled_jobs:
                self.output.write(f"ID: {job['id']}")
                self.output.write(f"Name: {job['name']}")
                self.output.write(f"Next run: {job['next_run_time']}")
                self.output.write(f"Trigger: {job['trigger']}")
                self.output.write_separator("-", 30)
        else:
            self.output.write("No jobs currently scheduled")
