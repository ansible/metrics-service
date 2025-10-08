"""
Django management command to manage the cron-based task scheduler.

This command provides utilities for managing the cron scheduler,
including starting, stopping, and listing scheduled tasks.
"""

import logging

from django.core.management.base import BaseCommand, CommandError

from apps.tasks.cron_scheduler import get_scheduler, start_scheduler, stop_scheduler

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """Management command to manage the cron-based task scheduler."""

    help = "Manage the cron-based task scheduler"

    def add_arguments(self, parser):
        """Add command arguments."""
        parser.add_argument(
            "action",
            choices=["start", "stop", "status", "list", "add", "remove"],
            help="Action to perform on the scheduler",
        )
        parser.add_argument("--task-id", help="Task ID for add/remove operations")
        parser.add_argument("--function", help="Function name for add operation")
        parser.add_argument("--cron", help="Cron expression for add operation")
        parser.add_argument("--args", help="JSON string of arguments for add operation")
        parser.add_argument("--description", help="Description for add operation")

    def handle(self, *args, **options):
        """Handle the command execution."""
        action = options["action"]

        try:
            if action == "start":
                self._start_scheduler()
            elif action == "stop":
                self._stop_scheduler()
            elif action == "status":
                self._show_status()
            elif action == "list":
                self._list_tasks()
            elif action == "add":
                self._add_task(options)
            elif action == "remove":
                self._remove_task(options)
        except Exception as e:
            raise CommandError(f"Error executing action '{action}': {str(e)}") from e

    def _start_scheduler(self):
        """Start the cron scheduler."""
        try:
            scheduler = start_scheduler()
            self.stdout.write(self.style.SUCCESS("Cron scheduler started successfully"))

            # Show registered tasks
            tasks = scheduler.list_tasks()
            self.stdout.write(f"Registered {len(tasks['registry'])} tasks:")
            for task_id, config in tasks["registry"].items():
                self.stdout.write(f"  - {task_id}: {config['cron']} ({config['function']})")

        except Exception as e:
            raise CommandError(f"Failed to start scheduler: {str(e)}") from e

    def _stop_scheduler(self):
        """Stop the cron scheduler."""
        try:
            stop_scheduler()
            self.stdout.write(self.style.SUCCESS("Cron scheduler stopped successfully"))
        except Exception as e:
            raise CommandError(f"Failed to stop scheduler: {str(e)}") from e

    def _show_status(self):
        """Show scheduler status."""
        try:
            scheduler = get_scheduler()
            if scheduler.running:
                self.stdout.write(self.style.SUCCESS("Scheduler is running"))

                # Show job status
                jobs = scheduler.list_tasks()
                self.stdout.write(f"\nScheduled jobs ({len(jobs['scheduled_jobs'])}):")
                for job in jobs["scheduled_jobs"]:
                    next_run = job["next_run_time"]
                    self.stdout.write(f"  - {job['id']}: {job['name']}")
                    self.stdout.write(f"    Next run: {next_run}")
                    self.stdout.write(f"    Trigger: {job['trigger']}")
            else:
                self.stdout.write(self.style.WARNING("Scheduler is not running"))
        except Exception as e:
            raise CommandError(f"Failed to get scheduler status: {str(e)}") from e

    def _list_tasks(self):
        """List all registered tasks."""
        try:
            scheduler = get_scheduler()
            tasks = scheduler.list_tasks()

            self.stdout.write("Registered tasks:")
            for task_id, config in tasks["registry"].items():
                enabled = "✓" if config.get("enabled", True) else "✗"
                self.stdout.write(f"  {enabled} {task_id}")
                self.stdout.write(f"    Function: {config['function']}")
                self.stdout.write(f"    Cron: {config['cron']}")
                self.stdout.write(f"    Description: {config.get('description', 'N/A')}")
                self.stdout.write("")

        except Exception as e:
            raise CommandError(f"Failed to list tasks: {str(e)}") from e

    def _add_task(self, options):
        """Add a new task to the scheduler."""
        task_id = options.get("task_id")
        function = options.get("function")
        cron = options.get("cron")
        args_str = options.get("args", "{}")
        description = options.get("description", "")

        if not all([task_id, function, cron]):
            raise CommandError("--task-id, --function, and --cron are required for add operation")

        try:
            import json

            args = json.loads(args_str)
        except json.JSONDecodeError as e:
            raise CommandError("Invalid JSON in --args") from e

        try:
            scheduler = get_scheduler()
            scheduler.add_dynamic_task(
                task_id=task_id, function_name=function, cron_expression=cron, args=args, description=description
            )
            self.stdout.write(self.style.SUCCESS(f"Added task '{task_id}' successfully"))
        except Exception as e:
            raise CommandError(f"Failed to add task: {str(e)}") from e

    def _remove_task(self, options):
        """Remove a task from the scheduler."""
        task_id = options.get("task_id")
        if not task_id:
            raise CommandError("--task-id is required for remove operation")

        try:
            scheduler = get_scheduler()
            scheduler.remove_task(task_id)
            self.stdout.write(self.style.SUCCESS(f"Removed task '{task_id}' successfully"))
        except Exception as e:
            raise CommandError(f"Failed to remove task: {str(e)}") from e
