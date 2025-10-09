"""
Fixed Django management command for the metrics service.

This version ensures dispatcherd uses the same configuration as the standalone
run_dispatcherd command, fixing the configuration inconsistency issue.
"""

import sys
from typing import Any

from django.core.management.base import BaseCommand, CommandError

from apps.core.services import (
    OutputFormatter,
    ProcessManager,
    ServiceConfig,
)


class Command(BaseCommand):
    """
    Fixed management command for the metrics service.

    This command ensures dispatcherd uses the same configuration as the
    standalone run_dispatcherd command.
    """

    help = "Metrics service management - unified entry point for all service operations"

    def __init__(self, *args, **kwargs):
        """Initialize the command with service instances."""
        super().__init__(*args, **kwargs)
        self.output = OutputFormatter(self.stdout, self.style)
        self.process_manager = ProcessManager(self.output)

    def add_arguments(self, parser):
        """Add command line arguments."""
        # Main subcommands
        subparsers = parser.add_subparsers(dest="command", help="Available commands", required=True)

        # Run command (main service)
        run_parser = subparsers.add_parser("run", help="Run the complete metrics service")
        self._add_run_arguments(run_parser)

        # Init commands
        subparsers.add_parser("init-service-id", help="Initialize ServiceID for ansible-base")
        init_tasks_parser = subparsers.add_parser("init-system-tasks", help="Initialize system tasks")
        self._add_init_tasks_arguments(init_tasks_parser)

        # Task management
        tasks_parser = subparsers.add_parser("tasks", help="Manage database tasks")
        self._add_task_management_arguments(tasks_parser)

        # Cron management
        cron_parser = subparsers.add_parser("cron", help="Manage cron-based task scheduler")
        self._add_cron_management_arguments(cron_parser)

    def _add_run_arguments(self, parser):
        """Add arguments for the run command."""
        parser.add_argument(
            "--host",
            default="127.0.0.1",
            help="Host to bind the Django server to (default: 127.0.0.1)",
        )
        parser.add_argument(
            "--port",
            default="8000",
            help="Port to bind the Django server to (default: 8000)",
        )
        parser.add_argument(
            "--workers",
            type=int,
            default=4,
            help="Number of dispatcher worker processes (default: 4)",
        )
        parser.add_argument(
            "--timeout",
            type=int,
            default=3600,
            help="Task timeout in seconds (default: 3600)",
        )
        parser.add_argument(
            "--max-tasks",
            type=int,
            default=100,
            help="Maximum tasks per worker before respawn (default: 100)",
        )
        parser.add_argument(
            "--log-level",
            choices=["DEBUG", "INFO", "WARNING", "ERROR"],
            default="INFO",
            help="Log level for both services (default: INFO)",
        )

    def _add_init_tasks_arguments(self, parser):
        """Add arguments for the init_system_tasks command."""
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be done without making changes",
        )
        parser.add_argument(
            "--list",
            action="store_true",
            help="List current system tasks",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Force update all system tasks even if no changes detected",
        )

    def _add_task_management_arguments(self, parser):
        """Add arguments for task management."""
        task_subparsers = parser.add_subparsers(dest="task_action", help="Task management actions", required=True)

        # Create task
        create_parser = task_subparsers.add_parser("create", help="Create a new task")
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
        list_parser = task_subparsers.add_parser("list", help="List tasks")
        list_parser.add_argument("--status", help="Filter by status")
        list_parser.add_argument("--limit", type=int, default=20, help="Limit number of results")

        # Show task details
        show_parser = task_subparsers.add_parser("show", help="Show task details")
        show_parser.add_argument("task_id", type=int, help="Task ID")

        # Cancel task
        cancel_parser = task_subparsers.add_parser("cancel", help="Cancel a task")
        cancel_parser.add_argument("task_id", type=int, help="Task ID")

        # Retry task
        retry_parser = task_subparsers.add_parser("retry", help="Retry a failed task")
        retry_parser.add_argument("task_id", type=int, help="Task ID")

    def _add_cron_management_arguments(self, parser):
        """Add arguments for cron management."""
        cron_subparsers = parser.add_subparsers(dest="cron_action", help="Cron management actions", required=True)

        # Start scheduler
        cron_subparsers.add_parser("start", help="Start cron scheduler")

        # Stop scheduler
        cron_subparsers.add_parser("stop", help="Stop cron scheduler")

        # Show status
        cron_subparsers.add_parser("status", help="Show cron scheduler status")

        # List tasks
        cron_subparsers.add_parser("list", help="List cron tasks")

        # Add task
        add_parser = cron_subparsers.add_parser("add", help="Add a cron task")
        add_parser.add_argument("--task-id", help="Task ID for add operation")
        add_parser.add_argument("--function", help="Function name for add operation")
        add_parser.add_argument("--cron", help="Cron expression for add operation")
        add_parser.add_argument("--args", help="JSON string of arguments for add operation")
        add_parser.add_argument("--description", help="Description for add operation")

        # Remove task
        remove_parser = cron_subparsers.add_parser("remove", help="Remove a cron task")
        remove_parser.add_argument("--task-id", help="Task ID for remove operation")

    def handle(self, *args, **options):
        """
        Handle the command execution.

        Routes to the appropriate subcommand handler based on the command option.
        """
        command = options.get("command")

        try:
            if command == "run":
                self._handle_run_command(options)
            elif command == "init-service-id":
                self._handle_init_service_id_command()
            elif command == "init-system-tasks":
                self._handle_init_system_tasks_command(options)
            elif command == "tasks":
                self._handle_task_management_command(options)
            elif command == "cron":
                self._handle_cron_management_command(options)
            else:
                self.output.error(f"Unknown command: {command}")
                sys.exit(1)
        except CommandError as e:
            self.output.error(str(e))
            sys.exit(1)
        except Exception as e:
            self.output.error(f"Unexpected error: {e}")
            sys.exit(1)

    def _handle_run_command(self, options: dict[str, Any]) -> None:
        """Handle the run command to start the metrics service."""
        try:
            config = ServiceConfig(options)
            self.output.success("🚀 Starting metrics service with unified dispatcherd configuration...")
            self.process_manager.start_services(config.to_dict())
        except ValueError as e:
            raise CommandError(f"Configuration error: {e}") from e

    def _handle_init_service_id_command(self) -> None:
        """Handle the init-service-id command."""
        try:
            from ansible_base.resource_registry.models.service_identifier import ServiceID

            service_id_count = ServiceID.objects.count()

            if service_id_count == 0:
                service_id = ServiceID.objects.create()
                message = f"Created ServiceID: {service_id.pk}"
                self.output.success(message)
            else:
                existing = ServiceID.objects.first()
                message = f"ServiceID exists: {existing.pk}"
                self.output.warning(message)
        except Exception as e:
            raise CommandError(f"Failed to initialize ServiceID: {e}") from e

    def _handle_init_system_tasks_command(self, options: dict[str, Any]) -> None:
        """Handle the init_system_tasks command."""
        try:
            from apps.tasks.tasks import create_system_tasks
        except ImportError as e:
            raise CommandError(f"Failed to import system tasks module: {e}") from e

        # Handle --list option
        if options.get("list", False):
            self._list_system_tasks()
            return

        # Handle dry-run option
        if options.get("dry_run", False):
            self._handle_dry_run_system_tasks()
            return

        # Execute the initialization
        self._execute_system_tasks_initialization(create_system_tasks)

    def _handle_dry_run_system_tasks(self):
        """Handle dry run mode for system tasks initialization."""
        self.output.warning("🔧 System Tasks Initialization (DRY RUN)")
        self.output.write_separator()
        self.output.write("📝 This is a dry run - no changes will be made")
        self.output.write("")
        self._list_system_tasks()

    def _execute_system_tasks_initialization(self, create_system_tasks):
        """Execute the actual system tasks initialization."""
        self.output.success("🔧 System Tasks Initialization")
        self.output.write_separator()

        try:
            import time

            start_time = time.time()
            results = create_system_tasks()
            elapsed_time = time.time() - start_time

            self._display_system_tasks_results(results, elapsed_time)
        except Exception as e:
            raise CommandError(f"❌ Failed to initialize system tasks: {e}") from e

    def _display_system_tasks_results(self, results, elapsed_time):
        """Display the results of system tasks initialization."""
        # Display results summary
        self.output.write("")
        self.output.write("📊 Results:")
        if results.get("created", 0) > 0:
            self.output.write(f"  ✅ Created: {results['created']} tasks")
        if results.get("updated", 0) > 0:
            self.output.write(f"  🔄 Updated: {results['updated']} tasks")
        if results.get("skipped", 0) > 0:
            self.output.write(f"  ⏭️  Skipped: {results['skipped']} tasks (no changes needed)")
        self.output.write("")

        # Display task details
        self._display_task_details(results)

        # Display final summary
        self.output.write_separator()
        total_processed = results.get("created", 0) + results.get("updated", 0) + results.get("skipped", 0)
        self.output.success(f"✅ Processed {total_processed} system tasks in {elapsed_time:.2f} seconds")
        self.output.write("💡 Run 'metric-service init-system-tasks --list' to see current status")

    def _display_task_details(self, results):
        """Display detailed task information."""
        if not results.get("tasks", []):
            return

        self.output.write("📋 Task Details:")
        for task_info in results["tasks"]:
            if task_info.startswith("Created:"):
                self.output.write(f"  ✅ {task_info}")
            elif task_info.startswith("Updated:"):
                self.output.write(f"  🔄 {task_info}")
            elif task_info.startswith("Skipped:"):
                self.output.write(f"  ⏭️  {task_info}")
            elif task_info.startswith("Error"):
                self.output.write(f"  ❌ {task_info}")
            else:
                self.output.write(f"  ℹ️  {task_info}")
        self.output.write("")

    def _list_system_tasks(self):
        """List current system tasks."""
        try:
            from apps.tasks.models import Task

            system_tasks = Task.objects.filter(is_system_task=True).order_by("created")

            if not system_tasks.exists():
                self.output.write("📭 No system tasks found")
                return

            self.output.write("📋 Current System Tasks")
            self.output.write_separator()

            # Group tasks by category based on function names
            categories = {}
            for task in system_tasks:
                if "cleanup" in task.function_name:
                    category = "MAINTENANCE"
                elif "collect" in task.function_name:
                    category = "METRICS"
                else:
                    category = "OTHER"

                if category not in categories:
                    categories[category] = []
                categories[category].append(task)

            # Display tasks by category
            total_tasks = 0
            category_names = []

            for category, tasks in categories.items():
                self.output.write(f"\n🏷️  {category} ({len(tasks)} tasks)")
                self.output.write_separator("-", 40)

                for task in tasks:
                    status_icon = "⏳" if task.status == "pending" else "✅" if task.status == "completed" else "❌"
                    recurring_icon = "🔄" if task.is_recurring else "➡️"

                    self.output.write(f"  {status_icon} {recurring_icon} {task.name}")
                    self.output.write(f"    Function: {task.function_name}")
                    if task.cron_expression:
                        self.output.write(f"    Schedule: {task.cron_expression}")
                    self.output.write(f"    Priority: {task.priority} | Status: {task.status}")
                    self.output.write("")

                total_tasks += len(tasks)
                category_names.append(category.lower())

            self.output.write_separator()
            self.output.write(f"📊 Total: {total_tasks} system tasks")
            self.output.write(f"📂 Categories: {', '.join(category_names)}")

        except Exception as e:
            self.output.error(f"❌ Failed to list system tasks: {e}")

    def _handle_task_management_command(self, options: dict[str, Any]) -> None:
        """Handle task management commands."""
        # For now, delegate to the original implementation
        # TODO: Implement using TaskManager service
        self.output.warning("Task management commands not yet implemented in refactored version")
        self.output.write("Please use the original metrics_service command for task management")

    def _handle_cron_management_command(self, options: dict[str, Any]) -> None:
        """Handle cron management commands."""
        # For now, delegate to the original implementation
        # TODO: Implement using CronManager service
        self.output.warning("Cron management commands not yet implemented in refactored version")
        self.output.write("Please use the original metrics_service command for cron management")
