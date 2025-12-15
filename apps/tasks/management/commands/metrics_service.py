"""
Fixed Django management command for the metrics service.

This version ensures dispatcherd uses the same configuration as the standalone
run_dispatcherd command, fixing the configuration inconsistency issue.
"""

import json
import signal
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.tasks.models import Task
from apps.tasks.services import (
    OutputFormatter,
    ProcessManager,
)

User = get_user_model()

# Constants for repeated messages
MSG_CRON_NOT_AVAILABLE = "⚠️ Cron scheduler module not available"
LABEL_TASK_ID = "Task ID"


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
        self.shutdown_requested = False
        self.threads = []
        self.processes = []

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
        show_parser.add_argument("task_id", type=int, help=LABEL_TASK_ID)

        # Cancel task
        cancel_parser = task_subparsers.add_parser("cancel", help="Cancel a task")
        cancel_parser.add_argument("task_id", type=int, help=LABEL_TASK_ID)

        # Retry task
        retry_parser = task_subparsers.add_parser("retry", help="Retry a failed task")
        retry_parser.add_argument("task_id", type=int, help=LABEL_TASK_ID)

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
            config = self._extract_config(options)
            self._start_services(config)
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

            # Group and display tasks
            categories = self._categorize_tasks(system_tasks)
            self._display_categorized_tasks(categories)

        except Exception as e:
            self.output.error(f"❌ Failed to list system tasks: {e}")

    def _categorize_tasks(self, tasks):
        """Categorize tasks based on their function names."""
        categories = {}
        for task in tasks:
            category = self._get_task_category(task)
            if category not in categories:
                categories[category] = []
            categories[category].append(task)
        return categories

    def _get_task_category(self, task):
        """Determine the category for a task based on its function name."""
        if "cleanup" in task.function_name:
            return "MAINTENANCE"
        if "collect" in task.function_name:
            return "METRICS"
        return "OTHER"

    def _display_categorized_tasks(self, categories):
        """Display tasks organized by category."""
        total_tasks = 0
        category_names = []

        for category, tasks in categories.items():
            self._display_category_section(category, tasks)
            total_tasks += len(tasks)
            category_names.append(category.lower())

        self._display_summary(total_tasks, category_names)

    def _display_category_section(self, category, tasks):
        """Display a category section with its tasks."""
        self.output.write(f"\n🏷️  {category} ({len(tasks)} tasks)")
        self.output.write_separator("-", 40)

        for task in tasks:
            self._display_single_task(task)

    def _display_single_task(self, task):
        """Display information for a single task."""
        if task.status == "pending":
            status_icon = "⏳"
        elif task.status == "completed":
            status_icon = "✅"
        else:
            status_icon = "❌"

        recurring_icon = "🔄" if task.is_recurring else "➡️"

        self.output.write(f"  {status_icon} {recurring_icon} {task.name}")
        self.output.write(f"    Function: {task.function_name}")
        if task.cron_expression:
            self.output.write(f"    Schedule: {task.cron_expression}")
        self.output.write(f"    Priority: {task.priority} | Status: {task.status}")
        self.output.write("")

    def _display_summary(self, total_tasks, category_names):
        """Display summary statistics."""
        self.output.write_separator()
        self.output.write(f"📊 Total: {total_tasks} system tasks")
        self.output.write(f"📂 Categories: {', '.join(category_names)}")

    def _handle_task_create(self, options: dict[str, Any]) -> None:
        """Handle task creation."""
        try:
            # Parse task data if provided
            task_data = {}
            if options.get("data"):
                try:
                    task_data = json.loads(options["data"])
                except json.JSONDecodeError as e:
                    raise CommandError(f"Invalid JSON data: {e}") from e

            # Parse scheduled time if provided
            scheduled_time = None
            if options.get("scheduled_time"):
                try:
                    scheduled_time = datetime.strptime(options["scheduled_time"], "%Y-%m-%d %H:%M:%S")
                    scheduled_time = timezone.make_aware(scheduled_time)
                except ValueError as e:
                    raise CommandError(f"Invalid scheduled time format. Use YYYY-MM-DD HH:MM:SS: {e}") from e

            # Get user if specified
            created_by = None
            if options.get("user"):
                try:
                    created_by = User.objects.get(username=options["user"])
                except User.DoesNotExist as e:
                    raise CommandError(f"User '{options['user']}' not found") from e

            # Create the task
            task = Task.objects.create(
                name=options["name"],
                function_name=options["function"],
                task_data=task_data,
                description=options.get("description", ""),
                scheduled_time=scheduled_time,
                cron_expression=options.get("cron"),
                is_recurring=options.get("recurring", False),
                priority=options.get("priority", 2),
                created_by=created_by,
            )

            self.output.success(f"✅ Created task: {task.name} (ID: {task.id})")

        except Exception as e:
            raise CommandError(f"Failed to create task: {e}") from e

    def _handle_task_list(self, options: dict[str, Any]) -> None:
        """Handle task listing."""
        queryset = Task.objects.all()

        # Apply status filter if provided
        if options.get("status"):
            queryset = queryset.filter(status=options["status"])

        # Apply limit
        limit = options.get("limit", 20)
        tasks = queryset.order_by("-created")[:limit]

        if not tasks:
            self.output.write("📭 No tasks found")
            return

        self.output.write(f"📋 Tasks (showing up to {limit} results)")
        self.output.write_separator()

        for task in tasks:
            status_icon = {"pending": "⏳", "running": "🔄", "completed": "✅", "failed": "❌", "cancelled": "⏹️"}.get(
                task.status, "❓"
            )
            self.output.write(f"{status_icon} {task.name} (ID: {task.id})")
            self.output.write(f"    Status: {task.status} | Function: {task.function_name}")
            if task.created_by:
                self.output.write(f"    Created by: {task.created_by.username}")
            self.output.write("")

    def _handle_task_show(self, options: dict[str, Any]) -> None:
        """Handle showing task details."""
        task_id = options["task_id"]
        try:
            task = Task.objects.get(id=task_id)
        except Task.DoesNotExist as e:
            raise CommandError(f"Task with ID {task_id} not found") from e

        self.output.write(f"📋 Task Details: {task.name}")
        self.output.write_separator()
        self.output.write(f"ID: {task.id}")
        self.output.write(f"Name: {task.name}")
        self.output.write(f"Function: {task.function_name}")
        self.output.write(f"Status: {task.status}")
        self.output.write(f"Priority: {task.priority}")
        if task.description:
            self.output.write(f"Description: {task.description}")
        if task.task_data:
            self.output.write(f"Data: {json.dumps(task.task_data, indent=2)}")
        if task.created_by:
            self.output.write(f"Created by: {task.created_by.username}")
        self.output.write(f"Created: {task.created}")
        if task.scheduled_time:
            self.output.write(f"Scheduled: {task.scheduled_time}")
        if task.cron_expression:
            self.output.write(f"Cron: {task.cron_expression}")

    def _handle_task_cancel(self, options: dict[str, Any]) -> None:
        """Handle task cancellation."""
        task_id = options["task_id"]
        try:
            task = Task.objects.get(id=task_id)
        except Task.DoesNotExist as e:
            raise CommandError(f"Task with ID {task_id} not found") from e

        if task.status in ["pending", "running"]:
            task.status = "cancelled"
            task.save()
            self.output.success(f"✅ Cancelled task: {task.name}")
        else:
            self.output.warning(f"⚠️ Task {task.name} is in '{task.status}' state and cannot be cancelled")

    def _handle_task_retry(self, options: dict[str, Any]) -> None:
        """Handle task retry."""
        task_id = options["task_id"]
        try:
            task = Task.objects.get(id=task_id)
        except Task.DoesNotExist as e:
            raise CommandError(f"Task with ID {task_id} not found") from e

        if task.status == "failed":
            task.status = "pending"
            task.save()
            self.output.success(f"✅ Retrying task: {task.name}")
        else:
            self.output.warning(f"⚠️ Task {task.name} is in '{task.status}' state and cannot be retried")

    def _handle_cron_start(self) -> None:
        """Handle cron scheduler start."""
        try:
            from apps.tasks.cron_scheduler import start_scheduler

            start_scheduler()
            self.output.success("✅ Cron scheduler started")
        except ImportError:
            self.output.warning(MSG_CRON_NOT_AVAILABLE)
        except Exception as e:
            self.output.error(f"❌ Failed to start cron scheduler: {e}")

    def _handle_cron_stop(self) -> None:
        """Handle cron scheduler stop."""
        try:
            from apps.tasks.cron_scheduler import stop_scheduler

            stop_scheduler()
            self.output.success("✅ Cron scheduler stopped")
        except ImportError:
            self.output.warning(MSG_CRON_NOT_AVAILABLE)
        except Exception as e:
            self.output.error(f"❌ Failed to stop cron scheduler: {e}")

    def _handle_cron_status(self) -> None:
        """Handle cron scheduler status."""
        try:
            from apps.tasks.cron_scheduler import get_scheduler

            scheduler = get_scheduler()
            if hasattr(scheduler, "running") and scheduler.running:
                self.output.success("✅ Cron scheduler is running")
            else:
                self.output.warning("⚠️ Cron scheduler is not running")
        except ImportError:
            self.output.warning(MSG_CRON_NOT_AVAILABLE)
        except Exception as e:
            self.output.error(f"❌ Failed to check cron scheduler status: {e}")

    def _handle_cron_list(self) -> None:
        """Handle cron jobs listing."""
        try:
            from apps.tasks.cron_scheduler import get_scheduler

            scheduler = get_scheduler()
            jobs = scheduler.get_jobs() if hasattr(scheduler, "get_jobs") else []

            if not jobs:
                self.output.write("📭 No cron jobs found")
                return

            self.output.write("📋 Cron Jobs")
            self.output.write_separator()
            for job in jobs:
                self.output.write(f"🕒 {getattr(job, 'id', 'Unknown ID')}")
                if hasattr(job, "func"):
                    self.output.write(f"    Function: {job.func}")
                if hasattr(job, "next_run_time"):
                    self.output.write(f"    Next run: {job.next_run_time}")
                self.output.write("")
        except ImportError:
            self.output.warning(MSG_CRON_NOT_AVAILABLE)
        except Exception as e:
            self.output.error(f"❌ Failed to list cron jobs: {e}")

    def _handle_cron_add(self, options: dict[str, Any]) -> None:
        """Handle adding cron job."""
        self.output.warning("⚠️ Cron add functionality not yet implemented")

    def _handle_cron_remove(self, options: dict[str, Any]) -> None:
        """Handle removing cron job."""
        self.output.warning("⚠️ Cron remove functionality not yet implemented")

    def _setup_signal_handlers(self) -> None:
        """Setup signal handlers for graceful shutdown."""

        def signal_handler(sig, frame):
            self.output.warning(f"Received signal {sig}, shutting down...")
            self.shutdown_requested = True

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

    def _initialize_service_state(self) -> None:
        """Initialize service state variables."""
        self.shutdown_requested = False
        self.threads = []
        self.processes = []

    def _cleanup_processes_and_threads(self) -> None:
        """Clean up processes and threads."""
        # Clean up processes
        for process in self.processes:
            if process.poll() is None:  # Process is still running
                try:
                    process.terminate()
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()

        # Clean up threads
        for thread in self.threads:
            if thread.is_alive():
                thread.join(timeout=5)

    def _start_services(self, config: dict[str, Any]) -> None:
        """Start services with the given configuration."""
        try:
            self._initialize_service_state()
            self._setup_signal_handlers()

            self.output.success("Starting metrics service:")
            self.output.write(f"Django server: http://{config['host']}:{config['port']}")
            self.output.write(f"Dispatcher workers: {config['workers']}")
            self.output.write("Task scheduler: APScheduler with cron support")

            # Start Django server
            self._start_django_thread(config)

            # Start dispatcher
            self._start_dispatcher_thread(config)

            # Start task scheduler
            self._start_scheduler_thread(config)

            # Monitor services
            self._monitor_services(config)

        except Exception as e:
            self.output.error(f"Start failed: {e}")
            sys.exit(1)

    def _start_django_thread(self, config: dict[str, Any]) -> None:
        """Start Django server in a thread."""
        import threading

        def django_runner():
            self._run_django_server(config["host"], config["port"], config["log_level"])

        thread = threading.Thread(target=django_runner, daemon=True)
        thread.start()
        self.threads.append(thread)

    def _start_dispatcher_thread(self, config: dict[str, Any]) -> None:
        """Start dispatcher in a thread."""
        import threading

        def dispatcher_runner():
            self._run_dispatcherd(config["workers"], config["timeout"], config["max_tasks"], config["log_level"])

        thread = threading.Thread(target=dispatcher_runner, daemon=True)
        thread.start()
        self.threads.append(thread)

    def _start_scheduler_thread(self, config: dict[str, Any]) -> None:
        """Start task scheduler in a thread."""
        import threading

        def scheduler_runner():
            self._run_task_scheduler(config["log_level"])

        thread = threading.Thread(target=scheduler_runner, daemon=True)
        thread.start()
        self.threads.append(thread)

    def _monitor_services(self, config: dict[str, Any]) -> None:
        """Monitor running services."""
        import time

        self.output.write(f"Django server started on http://{config['host']}:{config['port']}")
        self.output.write(f"Dispatcher started with {config['workers']} workers")
        self.output.write("Task scheduler started with cron support")
        self.output.write("Metrics service is running (Press Ctrl+C to stop)")

        while not self.shutdown_requested:
            # Check if any threads have died
            for i, thread in enumerate(self.threads):
                if not thread.is_alive():
                    if i == 0:  # Django thread
                        self.output.error("Django server thread stopped unexpectedly")
                    elif i == 1:  # Dispatcher thread
                        self.output.error("Dispatcher thread stopped unexpectedly")
                    elif i == 2:  # Scheduler thread
                        self.output.error("Task scheduler thread stopped unexpectedly")
                    self.shutdown_requested = True
                    break

            time.sleep(1)

        self._cleanup_processes_and_threads()

    def _run_task_scheduler(self, log_level: str) -> None:
        """Run task scheduler with APScheduler."""
        try:
            import logging
            import time

            # Configure logging level
            log_level_value = getattr(logging, log_level, logging.INFO)
            logging.getLogger("apscheduler").setLevel(log_level_value)

            # Import and start the scheduler
            from apps.tasks.cron_scheduler import get_scheduler, start_scheduler

            self.output.write("[Scheduler] Starting task scheduler...")
            start_scheduler()
            scheduler = get_scheduler()
            self.output.write("[Scheduler] Task scheduler started successfully")

            # Keep the scheduler running
            while not self.shutdown_requested:
                time.sleep(1)
                if not scheduler.running:
                    self.output.error("[Scheduler] Scheduler stopped unexpectedly")
                    break

        except ImportError as e:
            self.output.error(f"[Scheduler] Failed to import scheduler: {e}")
        except Exception as e:
            self.output.error(f"[Scheduler] Scheduler error: {e}")

    def _run_dispatcherd(self, workers: int, timeout: int, max_tasks: int, log_level: str) -> None:
        """Run dispatcherd process."""
        try:
            cmd = self._build_dispatcher_command(workers, timeout, max_tasks, log_level)
            process = self._start_dispatcher_process(cmd)
            if process:
                self._monitor_dispatcher_process(process)
        except Exception as e:
            self.output.error(f"Dispatcher error: {e}")

    def _start_dispatcher_process(self, cmd: list[str]) -> subprocess.Popen:
        """Start dispatcher process."""
        try:
            process = subprocess.Popen(  # noqa: S603  # Command is internally constructed and validated
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True, bufsize=1
            )
            self.processes.append(process)
            return process
        except Exception as e:
            self.output.error(f"Dispatcher error: {e}")
            return None

    def _monitor_dispatcher_process(self, process: subprocess.Popen) -> None:
        """Monitor dispatcher process."""
        while not self.shutdown_requested and process.poll() is None:
            line = process.stdout.readline()
            if line:
                self.output.write(f"[Dispatcher] {line.strip()}")

        if process.poll() is not None:
            self.output.write(f"Dispatcher process exited with code {process.poll()}")

    def _extract_config(self, options: dict[str, Any]) -> dict[str, Any]:
        """Extract configuration from command options."""
        return {
            "host": options.get("host", "127.0.0.1"),
            "port": options.get("port", "8000"),
            "workers": options.get("workers", 4),
            "timeout": options.get("timeout", 3600),
            "max_tasks": options.get("max_tasks", 100),
            "log_level": options.get("log_level", "INFO"),
        }

    def _build_dispatcher_command(self, workers: int, timeout: int, max_tasks: int, log_level: str) -> list[str]:
        """Build dispatcher command with validation."""
        # Validation
        if not isinstance(workers, int) or workers <= 0:
            raise ValueError(f"Invalid workers count: {workers}")
        if not isinstance(timeout, int) or timeout <= 0:
            raise ValueError(f"Invalid timeout: {timeout}")
        if not isinstance(max_tasks, int) or max_tasks <= 0:
            raise ValueError(f"Invalid max_tasks: {max_tasks}")
        if log_level not in ["DEBUG", "INFO", "WARNING", "ERROR"]:
            raise ValueError(f"Invalid log_level: {log_level}")

        manage_py = Path(__file__).parent.parent.parent.parent.parent / "manage.py"
        cmd = [
            sys.executable,
            str(manage_py),
            "run_dispatcherd",
            f"--workers={workers}",
            f"--timeout={timeout}",
            f"--max-tasks={max_tasks}",
            f"--log-level={log_level}",
        ]
        return cmd

    def _run_django_server(self, host: str, port: str, log_level: str) -> None:
        """Run Django server with security validation."""
        try:
            # Validate inputs for security
            if not isinstance(host, str) or not all(c.isalnum() or c in ".:_-" for c in host):
                raise ValueError(f"Invalid host: {host}")
            if not isinstance(port, int | str) or not str(port).isdigit():
                raise ValueError(f"Invalid port: {port}")

            manage_py = Path(__file__).parent.parent.parent.parent.parent / "manage.py"

            # Check if manage.py exists
            if not manage_py.exists():
                self.output.error("manage.py not found")
                return

            cmd = [
                sys.executable,
                str(manage_py),
                "runserver",
                f"{host}:{port}",
                "--noreload",
            ]

            # Add verbosity for DEBUG level
            if log_level == "DEBUG":
                cmd.append("--verbosity=2")

            self.output.write(f"Starting Django server: {' '.join(cmd)}")

            # Start the Django server process
            process = subprocess.Popen(  # noqa: S603  # Command is internally constructed and validated
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True, bufsize=1
            )
            self.processes.append(process)

            # Monitor the process
            while not self.shutdown_requested and process.poll() is None:
                line = process.stdout.readline()
                if line:
                    self.output.write(f"[Django] {line.strip()}")

            if process.poll() is not None:
                self.output.write(f"Django server process exited with code {process.poll()}")

        except Exception as e:
            self.output.error(f"Failed to start Django server: {e}")

    def _handle_task_management_command(self, options: dict[str, Any]) -> None:
        """Handle task management commands."""
        action = options.get("task_action")

        try:
            if action == "create":
                self._handle_task_create(options)
            elif action == "list":
                self._handle_task_list(options)
            elif action == "show":
                self._handle_task_show(options)
            elif action == "cancel":
                self._handle_task_cancel(options)
            elif action == "retry":
                self._handle_task_retry(options)
            else:
                raise CommandError(f"Unknown task action: {action}")
        except Exception as e:
            self.output.error(f"Task management error: {e}")
            sys.exit(1)

    def _handle_cron_management_command(self, options: dict[str, Any]) -> None:
        """Handle cron management commands."""
        action = options.get("cron_action")

        try:
            if action == "start":
                self._handle_cron_start()
            elif action == "stop":
                self._handle_cron_stop()
            elif action == "status":
                self._handle_cron_status()
            elif action == "list":
                self._handle_cron_list()
            elif action == "add":
                self._handle_cron_add(options)
            elif action == "remove":
                self._handle_cron_remove(options)
            else:
                raise CommandError(f"Unknown cron action: {action}")
        except Exception as e:
            self.output.error(f"Cron management error: {e}")
            sys.exit(1)
