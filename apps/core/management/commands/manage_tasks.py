"""
Django management command to manage database tasks.
"""

import json
import logging
from datetime import datetime, timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.core.models import Task, TaskChain, TaskChainMembership,

logger = logging.getLogger(__name__)
User = get_user_model()


class Command(BaseCommand):
    """Management command to manage database tasks."""

    help = "Manage database tasks: create, list, cancel, retry"

    def add_arguments(self, parser):
        """Add command arguments."""
        subparsers = parser.add_subparsers(dest="action", help="Available actions")

        # Create task
        create_parser = subparsers.add_parser("create", help="Create a new task")
        create_parser.add_argument("--name", required=True, help="Task name")
        create_parser.add_argument("--function", required=True, help="Function name to execute")
        create_parser.add_argument("--data", help="JSON data for the task")
        create_parser.add_argument("--description", help="Task description")
        create_parser.add_argument("--scheduled-time", help="Schedule time (YYYY-MM-DD HH:MM:SS)")
        create_parser.add_argument("--cron", help="Cron expression for recurring tasks")
        create_parser.add_argument("--recurring", action="store_true", help="Mark as recurring")
        create_parser.add_argument("--priority", type=int, choices=[1, 2, 3, 4], default=2, help="Task priority")
        create_parser.add_argument("--user", help="Username of task creator")

        # List tasks
        list_parser = subparsers.add_parser("list", help="List tasks")
        list_parser.add_argument("--status", help="Filter by status")
        list_parser.add_argument("--limit", type=int, default=20, help="Limit number of results")

        # Show task details
        show_parser = subparsers.add_parser("show", help="Show task details")
        show_parser.add_argument("task_id", type=int, help="Task ID")

        # Cancel task
        cancel_parser = subparsers.add_parser("cancel", help="Cancel a task")
        cancel_parser.add_argument("task_id", type=int, help="Task ID to cancel")

        # Retry task
        retry_parser = subparsers.add_parser("retry", help="Retry a failed task")
        retry_parser.add_argument("task_id", type=int, help="Task ID to retry")

        # Create dependency
        dep_parser = subparsers.add_parser("add-dependency", help="Add task dependency")
        dep_parser.add_argument("--dependent", type=int, required=True, help="Dependent task ID")
        dep_parser.add_argument("--prerequisite", type=int, required=True, help="Prerequisite task ID")
        dep_parser.add_argument("--status", default="completed", help="Required status of prerequisite")

        # Create chain
        chain_parser = subparsers.add_parser("create-chain", help="Create task chain")
        chain_parser.add_argument("--name", required=True, help="Chain name")
        chain_parser.add_argument("--description", help="Chain description")
        chain_parser.add_argument("--tasks", required=True, help="Comma-separated task IDs in order")

        # Clean up old tasks
        cleanup_parser = subparsers.add_parser("cleanup", help="Clean up old completed tasks")
        cleanup_parser.add_argument("--days", type=int, default=30, help="Days to keep completed tasks")
        cleanup_parser.add_argument("--dry-run", action="store_true", help="Show what would be deleted")

    def handle(self, *args, **options):
        """Handle the command execution."""
        action = options["action"]

        if not action:
            self.print_help("manage.py", "manage_tasks")
            return

        try:
            self._execute_action(action, options)
        except Exception as e:
            logger.error(f"Command failed: {str(e)}")
            raise CommandError(str(e)) from e

    def _execute_action(self, action, options):
        """Execute the specified action with the given options."""
        action_handlers = {
            "create": self.create_task,
            "list": self.list_tasks,
            "show": self.show_task,
            "cancel": self.cancel_task,
            "retry": self.retry_task,
            "add-dependency": self.add_dependency,
            "create-chain": self.create_chain,
            "cleanup": self.cleanup_tasks,
        }

        handler = action_handlers.get(action)
        if handler:
            handler(options)
        else:
            raise CommandError(f"Unknown action: {action}")

    def create_task(self, options):
        """Create a new task."""
        task_data = {}
        if options["data"]:
            try:
                task_data = json.loads(options["data"])
            except json.JSONDecodeError as e:
                raise CommandError(f"Invalid JSON data: {e}") from e

        scheduled_time = None
        if options["scheduled_time"]:
            try:
                scheduled_time = datetime.strptime(options["scheduled_time"], "%Y-%m-%d %H:%M:%S")
                scheduled_time = timezone.make_aware(scheduled_time)
            except ValueError as e:
                raise CommandError(f"Invalid date format: {e}") from e

        created_by = None
        if options["user"]:
            try:
                created_by = User.objects.get(username=options["user"])
            except User.DoesNotExist as e:
                raise CommandError(f"User '{options['user']}' not found") from e

        task = Task.objects.create(
            name=options["name"],
            function_name=options["function"],
            task_data=task_data,
            scheduled_time=scheduled_time,
            cron_expression=options["cron"],
            is_recurring=options["recurring"],
            priority=options["priority"],
            created_by=created_by,
        )

        self.stdout.write(self.style.SUCCESS(f"Created task: {task.name} (ID: {task.id})"))

    def list_tasks(self, options):
        """List tasks."""
        queryset = Task.objects.all()

        if options["status"]:
            queryset = queryset.filter(status=options["status"])

        queryset = queryset.order_by("-created")[: options["limit"]]

        if not queryset.exists():
            self.stdout.write("No tasks found.")
            return

        self.stdout.write("\nTasks:")
        self.stdout.write("-" * 80)
        for task in queryset:
            status_color = {
                "pending": self.style.WARNING,
                "running": self.style.HTTP_INFO,
                "completed": self.style.SUCCESS,
                "failed": self.style.ERROR,
                "cancelled": self.style.NOTICE,
            }.get(task.status, self.style.NOTICE)

            status_display = task.status.upper()
            self.stdout.write(
                f"ID: {task.id:4d} | {status_color(status_display):12} | "
                f"{task.name:30} | {task.function_name:20} | "
                f"Created: {task.created.strftime('%Y-%m-%d %H:%M')}"
            )

    def show_task(self, options):
        """Show detailed task information."""
        try:
            task = Task.objects.get(id=options["task_id"])
        except Task.DoesNotExist as e:
            raise CommandError(f"Task {options['task_id']} not found") from e

        self._display_task_header(task)
        self._display_task_basic_info(task)
        self._display_task_timing_info(task)
        self._display_task_data(task)
        self._show_dependencies(task)
        self._show_dependents(task)

    def _display_task_header(self, task):
        """Display task header information."""
        self.stdout.write(f"\nTask Details (ID: {task.id})")
        self.stdout.write("=" * 50)

    def _display_task_basic_info(self, task):
        """Display basic task information."""
        self.stdout.write(f"Name: {task.name}")
        if hasattr(task, "description") and task.description:
            self.stdout.write(f"Description: {task.description}")
        self.stdout.write(f"Function: {task.function_name}")
        self.stdout.write(f"Status: {task.get_status_display()}")
        self.stdout.write(f"Priority: {task.get_priority_display()}")
        self.stdout.write(f"Attempts: {task.attempts}/{task.max_attempts}")
        self.stdout.write(f"Created: {task.created}")
        self.stdout.write(f"Modified: {task.modified}")

    def _display_task_timing_info(self, task):
        """Display task timing information."""
        if task.scheduled_time:
            self.stdout.write(f"Scheduled: {task.scheduled_time}")
        if task.started_at:
            self.stdout.write(f"Started: {task.started_at}")
        if task.completed_at:
            self.stdout.write(f"Completed: {task.completed_at}")
        if task.cron_expression:
            self.stdout.write(f"Cron: {task.cron_expression}")
        if task.is_recurring:
            self.stdout.write("Recurring: Yes")
        if task.created_by:
            self.stdout.write(f"Created by: {task.created_by.username}")

    def _display_task_data(self, task):
        """Display task data and results."""
        self.stdout.write("\nTask Data:")
        self.stdout.write(json.dumps(task.task_data, indent=2))

        if task.result_data:
            self.stdout.write("\nResult Data:")
            self.stdout.write(json.dumps(task.result_data, indent=2))

        if task.error_message:
            self.stdout.write(f"\nError: {task.error_message}")

    def _show_dependencies(self, task):
        """Helper to show dependencies of a task."""
        dependencies = task.dependencies.all()
        if dependencies:
            self.stdout.write("\nDependencies:")
            for dep in dependencies:
                self.stdout.write(f"  - Requires {dep.prerequisite_task.name} to be {dep.required_status}")

    def _show_dependents(self, task):
        """Helper to show dependents of a task."""
        dependents = task.dependents.all()
        if dependents:
            self.stdout.write("\nDependent Tasks:")
            for dep in dependents:
                self.stdout.write(f"  - {dep.dependent_task.name} depends on this task")

    def cancel_task(self, options):
        """Cancel a task."""
        try:
            task = Task.objects.get(id=options["task_id"])
        except Task.DoesNotExist as e:
            raise CommandError(f"Task {options['task_id']} not found") from e

        if task.status in ["completed", "cancelled", "failed"]:
            raise CommandError(f"Cannot cancel task with status: {task.status}")

        task.status = "cancelled"
        task.save()

        self.stdout.write(self.style.SUCCESS(f"Cancelled task: {task.name} (ID: {task.id})"))

    def retry_task(self, options):
        """Retry a failed task."""
        try:
            task = Task.objects.get(id=options["task_id"])
        except Task.DoesNotExist as e:
            raise CommandError(f"Task {options['task_id']} not found") from e

        if not task.can_retry():
            raise CommandError(f"Cannot retry task: status={task.status}, attempts={task.attempts}/{task.max_attempts}")

        task.status = "pending"
        task.error_message = ""
        task.started_at = None
        task.completed_at = None
        task.save()

        self.stdout.write(self.style.SUCCESS(f"Reset task for retry: {task.name} (ID: {task.id})"))

    def add_dependency(self, options):
        """Add task dependency."""
        try:
            dependent_task = Task.objects.get(id=options["dependent"])
            prerequisite_task = Task.objects.get(id=options["prerequisite"])
        except Task.DoesNotExist as e:
            raise CommandError(f"Task not found: {e}") from e

        dependency, created = TaskDependency.objects.get_or_create(
            dependent_task=dependent_task,
            prerequisite_task=prerequisite_task,
            defaults={"required_status": options["status"]},
        )

        if created:
            self.stdout.write(
                self.style.SUCCESS(f"Added dependency: {dependent_task.name} depends on {prerequisite_task.name}")
            )
        else:
            self.stdout.write(self.style.WARNING("Dependency already exists"))

    def create_chain(self, options):
        """Create a task chain."""
        task_ids = [int(id.strip()) for id in options["tasks"].split(",")]

        # Verify all tasks exist
        tasks = []
        for task_id in task_ids:
            try:
                task = Task.objects.get(id=task_id)
                tasks.append(task)
            except Task.DoesNotExist as e:
                raise CommandError(f"Task {task_id} not found") from e

        # Create the chain
        chain = TaskChain.objects.create(name=options["name"])

        # Add tasks to chain
        for order, task in enumerate(tasks, 1):
            TaskChainMembership.objects.create(chain=chain, task=task, order=order)

        # Create dependencies between consecutive tasks
        for i in range(len(tasks) - 1):
            TaskDependency.objects.get_or_create(
                dependent_task=tasks[i + 1], prerequisite_task=tasks[i], required_status="completed"
            )

        self.stdout.write(self.style.SUCCESS(f"Created task chain: {chain.name} with {len(tasks)} tasks"))

    def cleanup_tasks(self, options):
        """Clean up old completed tasks."""
        cutoff_date = timezone.now() - timedelta(days=options["days"])

        old_tasks = Task.objects.filter(status__in=["completed", "failed", "cancelled"], completed_at__lt=cutoff_date)

        count = old_tasks.count()

        if options["dry_run"]:
            self.stdout.write(f"Would delete {count} tasks older than {options['days']} days")
            for task in old_tasks[:10]:  # Show first 10
                self.stdout.write(f"  - {task.name} (ID: {task.id}, completed: {task.completed_at})")
            if count > 10:
                self.stdout.write(f"  ... and {count - 10} more")
        else:
            old_tasks.delete()
            self.stdout.write(self.style.SUCCESS(f"Deleted {count} old tasks"))
