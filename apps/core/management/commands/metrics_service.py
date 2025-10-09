"""
Django management command to run the complete metrics service.

This command provides a unified entry point for all metrics service operations,
including running the service, managing tasks, and system initialization.
"""

import json
import logging
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from ansible_base.resource_registry.models.service_identifier import ServiceID

logger = logging.getLogger(__name__)
User = get_user_model()


class Command(BaseCommand):
    """
    Management command to run the complete metrics service.

    This command provides a unified entry point for all metrics service operations:
    - Running the complete service (Django + dispatcher + scheduler)
    - Managing database tasks
    - Managing cron scheduler
    - System initialization tasks
    """

    help = "Metric service management - unified entry point for all service operations"

    def add_arguments(self, parser):
        """
        Add command line arguments.

        Args:
            parser: ArgumentParser instance to add arguments to
        """
        # Main subcommands
        subparsers = parser.add_subparsers(dest="command", help="Available commands", required=True)

        # Run command (main service)
        run_parser = subparsers.add_parser("run", help="Run the complete metrics service")
        self._add_run_arguments(run_parser)

        # Init commands
        init_service_parser = subparsers.add_parser("init-service-id", help="Initialize ServiceID for ansible-base")
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
        # Django runserver arguments
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
        # Dispatcher arguments
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
        start_parser = cron_subparsers.add_parser("start", help="Start cron scheduler")

        # Stop scheduler
        stop_parser = cron_subparsers.add_parser("stop", help="Stop cron scheduler")

        # Show status
        status_parser = cron_subparsers.add_parser("status", help="Show cron scheduler status")

        # List tasks
        list_parser = cron_subparsers.add_parser("list", help="List cron tasks")

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

        Args:
            *args: Positional arguments (unused)
            **options: Command options
        """
        command = options.get("command")

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
            self.stdout.write(self.style.ERROR(f"Unknown command: {command}"))
            sys.exit(1)

    def _handle_run_command(self, options):
        """Handle the run command to start the metrics service."""
        config = self._extract_config(options)
        self._initialize_service_state()
        self._setup_signal_handlers()
        self._start_services(config)

    def _handle_init_service_id_command(self):
        """Handle the init-service-id command."""
        try:
            service_id_count = ServiceID.objects.count()

            if service_id_count == 0:
                service_id = ServiceID.objects.create()
                message = f"Created ServiceID: {service_id.pk}"
                self.stdout.write(self.style.SUCCESS(message))
            else:
                existing = ServiceID.objects.first()
                message = f"ServiceID exists: {existing.pk}"
                self.stdout.write(self.style.WARNING(message))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Failed to initialize ServiceID: {e}"))
            sys.exit(1)

    def _handle_init_system_tasks_command(self, options):
        """Handle the init_system_tasks command."""
        try:
            from apps.tasks.tasks import create_system_tasks, get_system_task_info
        except ImportError as e:
            self.stdout.write(self.style.ERROR(f"Failed to import system tasks module: {e}"))
            sys.exit(1)

        # Handle --list option
        if options.get("list", False):
            self._list_system_tasks()
            return

        # Handle dry-run and force options
        dry_run = options.get("dry_run", False)
        force = options.get("force", False)

        if dry_run:
            self.stdout.write(self.style.WARNING("🔧 System Tasks Initialization (DRY RUN)"))
            self.stdout.write("=" * 50)
            self.stdout.write("📝 This is a dry run - no changes will be made")
            self.stdout.write("")
            # For now, just show what would happen
            self._list_system_tasks()
            return

        # Execute the initialization
        self.stdout.write(self.style.SUCCESS("🔧 System Tasks Initialization"))
        self.stdout.write("=" * 50)

        try:
            import time

            start_time = time.time()

            results = create_system_tasks()

            elapsed_time = time.time() - start_time

            # Display results
            self.stdout.write("")
            self.stdout.write("📊 Results:")
            if results.get("created", 0) > 0:
                self.stdout.write(f"  ✅ Created: {results['created']} tasks")
            if results.get("updated", 0) > 0:
                self.stdout.write(f"  🔄 Updated: {results['updated']} tasks")
            if results.get("skipped", 0) > 0:
                self.stdout.write(f"  ⏭️  Skipped: {results['skipped']} tasks (no changes needed)")
            self.stdout.write("")

            # Display task details
            if results.get("tasks", []):
                self.stdout.write("📋 Task Details:")
                for task_info in results["tasks"]:
                    if task_info.startswith("Created:"):
                        self.stdout.write(f"  ✅ {task_info}")
                    elif task_info.startswith("Updated:"):
                        self.stdout.write(f"  🔄 {task_info}")
                    elif task_info.startswith("Skipped:"):
                        self.stdout.write(f"  ⏭️  {task_info}")
                    elif task_info.startswith("Error"):
                        self.stdout.write(f"  ❌ {task_info}")
                    else:
                        self.stdout.write(f"  ℹ️  {task_info}")
                self.stdout.write("")

            self.stdout.write("=" * 50)
            total_processed = results.get("created", 0) + results.get("updated", 0) + results.get("skipped", 0)
            self.stdout.write(
                self.style.SUCCESS(f"✅ Processed {total_processed} system tasks in {elapsed_time:.2f} seconds")
            )
            self.stdout.write("💡 Run 'metric-service init-system-tasks --list' to see current status")

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Failed to initialize system tasks: {e}"))
            sys.exit(1)

    def _handle_task_management_command(self, options):
        """Handle task management commands."""
        task_action = options.get("task_action")

        if task_action == "create":
            self._create_task(options)
        elif task_action == "list":
            self._list_tasks(options)
        elif task_action == "show":
            self._show_task(options)
        elif task_action == "cancel":
            self._cancel_task(options)
        elif task_action == "retry":
            self._retry_task(options)
        else:
            self.stdout.write(self.style.ERROR(f"Unknown task action: {task_action}"))
            sys.exit(1)

    def _handle_cron_management_command(self, options):
        """Handle cron management commands."""
        cron_action = options.get("cron_action")

        try:
            from apps.tasks.cron_scheduler import get_scheduler, start_scheduler, stop_scheduler
        except ImportError as e:
            self.stdout.write(self.style.ERROR(f"Failed to import cron scheduler: {e}"))
            sys.exit(1)

        if cron_action == "start":
            self._start_cron_scheduler()
        elif cron_action == "stop":
            self._stop_cron_scheduler()
        elif cron_action == "status":
            self._show_cron_status()
        elif cron_action == "list":
            self._list_cron_tasks()
        elif cron_action == "add":
            self._add_cron_task(options)
        elif cron_action == "remove":
            self._remove_cron_task(options)
        else:
            self.stdout.write(self.style.ERROR(f"Unknown cron action: {cron_action}"))
            sys.exit(1)

    # Task management methods
    def _create_task(self, options):
        """Create a new task."""
        try:
            from apps.tasks.models import Task

            # Parse task data
            task_data = {}
            if options.get("data"):
                try:
                    task_data = json.loads(options["data"])
                except json.JSONDecodeError:
                    raise CommandError("Invalid JSON in --data argument")

            # Parse scheduled time
            scheduled_time = None
            if options.get("scheduled_time"):
                try:
                    scheduled_time = datetime.strptime(options["scheduled_time"], "%Y-%m-%d %H:%M:%S")
                    scheduled_time = timezone.make_aware(scheduled_time)
                except ValueError:
                    raise CommandError("Invalid scheduled_time format. Use YYYY-MM-DD HH:MM:SS")

            # Get user
            user = None
            if options.get("user"):
                try:
                    user = User.objects.get(username=options["user"])
                except User.DoesNotExist:
                    raise CommandError(f"User '{options['user']}' not found")

            # Create task
            task = Task.objects.create(
                name=options["name"],
                function_name=options["function"],
                task_data=task_data,
                description=options.get("description", ""),
                scheduled_time=scheduled_time,
                cron_expression=options.get("cron"),
                is_recurring=options.get("recurring", False),
                priority=options["priority"],
                created_by=user,
            )

            self.stdout.write(self.style.SUCCESS(f"Created task {task.id}: {task.name}"))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Failed to create task: {e}"))
            sys.exit(1)

    def _list_tasks(self, options):
        """List tasks."""
        try:
            from apps.tasks.models import Task

            queryset = Task.objects.all()
            if options.get("status"):
                queryset = queryset.filter(status=options["status"])

            tasks = queryset.order_by("-created")[: options["limit"]]

            if not tasks:
                self.stdout.write("No tasks found")
                return

            self.stdout.write(f"Tasks (showing {len(tasks)} of {queryset.count()}):")
            self.stdout.write("-" * 80)
            for task in tasks:
                status_icon = "⏳" if task.status == "pending" else "✅" if task.status == "completed" else "❌"
                self.stdout.write(
                    f"{status_icon} {task.id:4d} | {task.name:<30} | {task.status:<10} | {task.function_name}"
                )

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Failed to list tasks: {e}"))
            sys.exit(1)

    def _show_task(self, options):
        """Show task details."""
        try:
            from apps.tasks.models import Task

            task_id = options["task_id"]
            task = Task.objects.get(id=task_id)

            self.stdout.write(f"Task Details - ID: {task.id}")
            self.stdout.write("=" * 50)
            self.stdout.write(f"Name: {task.name}")
            self.stdout.write(f"Function: {task.function_name}")
            self.stdout.write(f"Status: {task.status}")
            self.stdout.write(f"Priority: {task.priority}")
            self.stdout.write(f"Created: {task.created}")
            self.stdout.write(f"Description: {task.description or 'None'}")
            if task.scheduled_time:
                self.stdout.write(f"Scheduled: {task.scheduled_time}")
            if task.cron_expression:
                self.stdout.write(f"Cron: {task.cron_expression}")
            if task.task_data:
                self.stdout.write(f"Data: {json.dumps(task.task_data, indent=2)}")

        except Task.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"Task {options['task_id']} not found"))
            sys.exit(1)
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Failed to show task: {e}"))
            sys.exit(1)

    def _cancel_task(self, options):
        """Cancel a task."""
        try:
            from apps.tasks.models import Task

            task_id = options["task_id"]
            task = Task.objects.get(id=task_id)

            if task.status not in ["pending", "running"]:
                self.stdout.write(self.style.WARNING(f"Task {task_id} is not in a cancellable state ({task.status})"))
                return

            task.status = "cancelled"
            task.save()

            self.stdout.write(self.style.SUCCESS(f"Cancelled task {task_id}: {task.name}"))

        except Task.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"Task {options['task_id']} not found"))
            sys.exit(1)
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Failed to cancel task: {e}"))
            sys.exit(1)

    def _retry_task(self, options):
        """Retry a failed task."""
        try:
            from apps.tasks.models import Task

            task_id = options["task_id"]
            task = Task.objects.get(id=task_id)

            if task.status != "failed":
                self.stdout.write(self.style.WARNING(f"Task {task_id} is not in failed state ({task.status})"))
                return

            task.status = "pending"
            task.save()

            self.stdout.write(self.style.SUCCESS(f"Retried task {task_id}: {task.name}"))

        except Task.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"Task {options['task_id']} not found"))
            sys.exit(1)
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Failed to retry task: {e}"))
            sys.exit(1)

    # Cron management methods
    def _start_cron_scheduler(self):
        """Start the cron scheduler."""
        try:
            from apps.tasks.cron_scheduler import start_scheduler

            start_scheduler()
            self.stdout.write(self.style.SUCCESS("Cron scheduler started"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Failed to start cron scheduler: {e}"))
            sys.exit(1)

    def _stop_cron_scheduler(self):
        """Stop the cron scheduler."""
        try:
            from apps.tasks.cron_scheduler import stop_scheduler

            stop_scheduler()
            self.stdout.write(self.style.SUCCESS("Cron scheduler stopped"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Failed to stop cron scheduler: {e}"))
            sys.exit(1)

    def _show_cron_status(self):
        """Show cron scheduler status."""
        try:
            from apps.tasks.cron_scheduler import get_scheduler

            scheduler = get_scheduler()
            if scheduler.running:
                self.stdout.write(self.style.SUCCESS("Cron scheduler is running"))
            else:
                self.stdout.write(self.style.WARNING("Cron scheduler is not running"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Failed to get cron scheduler status: {e}"))
            sys.exit(1)

    def _list_cron_tasks(self):
        """List cron tasks."""
        try:
            from apps.tasks.cron_scheduler import get_scheduler

            scheduler = get_scheduler()
            jobs = scheduler.get_jobs()

            if not jobs:
                self.stdout.write("No cron tasks scheduled")
                return

            self.stdout.write(f"Cron Tasks ({len(jobs)}):")
            self.stdout.write("-" * 50)
            for job in jobs:
                self.stdout.write(f"ID: {job.id}")
                self.stdout.write(f"Function: {job.func}")
                self.stdout.write(f"Next run: {job.next_run_time}")
                self.stdout.write("-" * 30)

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Failed to list cron tasks: {e}"))
            sys.exit(1)

    def _add_cron_task(self, options):
        """Add a cron task."""
        self.stdout.write(self.style.WARNING("Add cron task functionality not yet implemented"))
        # TODO: Implement add cron task

    def _remove_cron_task(self, options):
        """Remove a cron task."""
        self.stdout.write(self.style.WARNING("Remove cron task functionality not yet implemented"))
        # TODO: Implement remove cron task

    def _list_system_tasks(self):
        """List current system tasks."""
        try:
            from apps.tasks.models import Task

            system_tasks = Task.objects.filter(is_system_task=True).order_by("created")

            if not system_tasks.exists():
                self.stdout.write("📭 No system tasks found")
                return

            self.stdout.write("📋 Current System Tasks")
            self.stdout.write("=" * 50)

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
                self.stdout.write(f"\n🏷️  {category} ({len(tasks)} tasks)")
                self.stdout.write("-" * 40)

                for task in tasks:
                    status_icon = "⏳" if task.status == "pending" else "✅" if task.status == "completed" else "❌"
                    recurring_icon = "🔄" if task.is_recurring else "➡️"

                    self.stdout.write(f"  {status_icon} {recurring_icon} {task.name}")
                    self.stdout.write(f"    Function: {task.function_name}")
                    if task.cron_expression:
                        self.stdout.write(f"    Schedule: {task.cron_expression}")
                    self.stdout.write(f"    Priority: {task.priority} | Status: {task.status}")
                    self.stdout.write("")

                total_tasks += len(tasks)
                category_names.append(category.lower())

            self.stdout.write("=" * 50)
            self.stdout.write(f"📊 Total: {total_tasks} system tasks")
            self.stdout.write(f"📂 Categories: {', '.join(category_names)}")

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Failed to list system tasks: {e}"))

    def _extract_config(self, options):
        """Extract configuration from command options."""
        return {
            "host": options["host"],
            "port": options["port"],
            "workers": options["workers"],
            "timeout": options["timeout"],
            "max_tasks": options["max_tasks"],
            "log_level": options["log_level"],
        }

    def _initialize_service_state(self):
        """Initialize shared state for service management."""
        self.shutdown_requested = False
        self.threads = []
        self.processes = []

    def _setup_signal_handlers(self):
        """Setup signal handlers for graceful shutdown."""

        def signal_handler(signum, frame):
            """Handle shutdown signals gracefully."""
            self.stdout.write(self.style.WARNING("Received shutdown signal..."))
            self.shutdown_requested = True
            self._cleanup_processes_and_threads()
            sys.exit(0)

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

    def _cleanup_processes_and_threads(self):
        """Clean up processes and threads during shutdown."""
        # Terminate processes
        for process in self.processes:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()

        # Wait for threads to finish
        for thread in self.threads:
            if thread.is_alive():
                thread.join(timeout=5)

    def _start_services(self, config):
        """Start Django server, dispatcher, and task scheduler services."""
        self.stdout.write(
            self.style.SUCCESS(
                f"Starting metrics service:\n"
                f"  Django server: http://{config['host']}:{config['port']}\n"
                f"  Dispatcher workers: {config['workers']}\n"
                f"  Task scheduler: enabled\n"
                f"  Log level: {config['log_level']}"
            )
        )

        try:
            self._start_django_thread(config)
            self._start_dispatcher_thread(config)
            self._start_task_scheduler_thread(config)
            self._monitor_services(config)
        except Exception as e:
            logger.error(f"Failed to start metrics service: {str(e)}")
            self.stdout.write(self.style.ERROR(f"Start failed: {str(e)}"))
            sys.exit(1)

    def _start_django_thread(self, config):
        """Start Django server in a separate thread."""
        runserver_thread = threading.Thread(
            target=self._run_django_server, args=(config["host"], config["port"], config["log_level"]), daemon=True
        )
        runserver_thread.start()
        self.threads.append(runserver_thread)

    def _start_dispatcher_thread(self, config):
        """Start dispatcher in a separate thread."""
        dispatcher_thread = threading.Thread(
            target=self._run_dispatcherd,
            args=(config["workers"], config["timeout"], config["max_tasks"], config["log_level"]),
            daemon=True,
        )
        dispatcher_thread.start()
        self.threads.append(dispatcher_thread)

    def _start_task_scheduler_thread(self, config):
        """Start task scheduler in a separate thread."""
        task_scheduler_thread = threading.Thread(
            target=self._run_task_scheduler,
            args=(config["log_level"],),
            daemon=True,
        )
        task_scheduler_thread.start()
        self.threads.append(task_scheduler_thread)

    def _monitor_services(self, config):
        """Monitor running services and handle failures."""
        self.stdout.write(
            self.style.SUCCESS(
                f"✓ Django server started on http://{config['host']}:{config['port']}\n"
                f"✓ Dispatcher started with {config['workers']} workers\n"
                f"✓ Task scheduler started\n"
                f"✓ Metrics service is running. Press Ctrl+C to stop."
            )
        )

        runserver_thread, dispatcher_thread, task_scheduler_thread = self.threads[:3]

        # Keep the main thread alive
        while not self.shutdown_requested:
            time.sleep(1)

            # Check if threads are still alive
            if not runserver_thread.is_alive():
                self.stdout.write(self.style.ERROR("Django server thread stopped unexpectedly"))
                break

            if not dispatcher_thread.is_alive():
                self.stdout.write(self.style.ERROR("Dispatcher thread stopped unexpectedly"))
                break

            if not task_scheduler_thread.is_alive():
                self.stdout.write(self.style.ERROR("Task scheduler thread stopped unexpectedly"))
                break

    def _run_django_server(self, host, port, log_level):
        """
        Run the Django development server.

        Args:
            host: Host to bind to
            port: Port to bind to
            log_level: Logging level
        """
        try:
            # Configure Django logging
            django_logger = logging.getLogger("django")
            django_logger.setLevel(getattr(logging, log_level))

            # Use subprocess to run runserver to avoid conflicts
            manage_py = Path(__file__).parent.parent.parent.parent.parent / "manage.py"

            # Validate inputs for security
            if not manage_py.exists():
                raise ValueError(f"manage.py not found at {manage_py}")

            # Sanitize host and port inputs
            if not isinstance(host, str) or not host.replace(".", "").replace(":", "").isalnum():
                raise ValueError(f"Invalid host: {host}")
            if not isinstance(port, int | str) or not str(port).isdigit():
                raise ValueError(f"Invalid port: {port}")

            cmd = [
                sys.executable,
                str(manage_py),
                "runserver",
                f"{host}:{port}",
                "--noreload",  # Disable auto-reload to prevent conflicts
            ]

            if log_level == "DEBUG":
                cmd.append("--verbosity=2")

            self.stdout.write(f"Starting Django server: {' '.join(cmd)}")
            # nosec B603 - command constructed from validated inputs
            process = subprocess.Popen(  # noqa: S603
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True, bufsize=1
            )

            # Store process reference for cleanup
            self.processes.append(process)

            # Stream output
            while not self.shutdown_requested and process.poll() is None:
                line = process.stdout.readline()
                if line:
                    self.stdout.write(f"[Django] {line.strip()}")

            if process.poll() is None:
                process.terminate()
                process.wait()

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Django server error: {str(e)}"))

    def _run_dispatcherd(self, workers, timeout, max_tasks, log_level):
        """
        Run the dispatcher service.

        Args:
            workers: Number of worker processes
            timeout: Task timeout in seconds
            max_tasks: Maximum tasks per worker
            log_level: Logging level
        """
        try:
            cmd = self._build_dispatcher_command(workers, timeout, max_tasks, log_level)
            process = self._start_dispatcher_process(cmd)
            if process:
                self._monitor_dispatcher_process(process)
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Dispatcher error: {str(e)}"))

    def _build_dispatcher_command(self, workers, timeout, max_tasks, log_level):
        """Build and validate dispatcher command."""
        manage_py = Path(__file__).parent.parent.parent.parent.parent / "manage.py"

        # Validate inputs for security
        if not manage_py.exists():
            raise ValueError(f"manage.py not found at {manage_py}")

        # Validate parameters
        if not isinstance(workers, int) or workers <= 0:
            raise ValueError(f"Invalid workers count: {workers}")
        if not isinstance(timeout, int) or timeout <= 0:
            raise ValueError(f"Invalid timeout: {timeout}")
        if not isinstance(max_tasks, int) or max_tasks <= 0:
            raise ValueError(f"Invalid max_tasks: {max_tasks}")
        if log_level not in ["DEBUG", "INFO", "WARNING", "ERROR"]:
            raise ValueError(f"Invalid log_level: {log_level}")

        return [
            sys.executable,
            str(manage_py),
            "run_dispatcherd",
            f"--workers={workers}",
            f"--timeout={timeout}",
            f"--max-tasks={max_tasks}",
            f"--log-level={log_level}",
        ]

    def _start_dispatcher_process(self, cmd):
        """Start the dispatcher process."""
        self.stdout.write(f"Starting dispatcher: {' '.join(cmd)}")
        try:
            # nosec B603 - command constructed from validated inputs
            process = subprocess.Popen(  # noqa: S603
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True, bufsize=1
            )
            self.processes.append(process)
            return process
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Dispatcher error: {str(e)}"))
            return None

    def _monitor_dispatcher_process(self, process):
        """Monitor dispatcher process output."""
        # Stream output
        while not self.shutdown_requested and process.poll() is None:
            line = process.stdout.readline()
            if line:
                self.stdout.write(f"[Dispatcher] {line.strip()}")

        if process.poll() is None:
            process.terminate()
            process.wait()

    def _run_task_scheduler(self, log_level):
        """
        Run the task scheduler service.

        Args:
            log_level: Logging level
        """
        try:
            cmd = self._build_task_scheduler_command(log_level)
            process = self._start_task_scheduler_process(cmd)
            if process:
                self._monitor_task_scheduler_process(process)
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Task scheduler error: {str(e)}"))

    def _build_task_scheduler_command(self, log_level):
        """Build and validate task scheduler command."""
        manage_py = Path(__file__).parent.parent.parent.parent.parent / "manage.py"

        # Validate inputs for security
        if not manage_py.exists():
            raise ValueError(f"manage.py not found at {manage_py}")

        if log_level not in ["DEBUG", "INFO", "WARNING", "ERROR"]:
            raise ValueError(f"Invalid log_level: {log_level}")

        return [
            sys.executable,
            str(manage_py),
            "run_task_scheduler",
            f"--log-level={log_level}",
        ]

    def _start_task_scheduler_process(self, cmd):
        """Start the task scheduler process."""
        self.stdout.write(f"Starting task scheduler: {' '.join(cmd)}")
        try:
            # nosec B603 - command constructed from validated inputs
            process = subprocess.Popen(  # noqa: S603
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True, bufsize=1
            )
            self.processes.append(process)
            return process
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Task scheduler error: {str(e)}"))
            return None

    def _monitor_task_scheduler_process(self, process):
        """Monitor task scheduler process output."""
        # Stream output
        while not self.shutdown_requested and process.poll() is None:
            line = process.stdout.readline()
            if line:
                self.stdout.write(f"[TaskScheduler] {line.strip()}")

        if process.poll() is None:
            process.terminate()
            process.wait()
