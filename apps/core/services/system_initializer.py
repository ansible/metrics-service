"""
System initialization service.

Handles system initialization tasks including ServiceID creation and
system task initialization.
"""

import time
from typing import Any, Dict

from ansible_base.resource_registry.models.service_identifier import ServiceID
from django.core.management.base import CommandError

from apps.tasks.models import Task


class SystemInitializer:
    """Manages system initialization for the metrics service."""

    def __init__(self, output_formatter):
        """
        Initialize the system initializer.

        Args:
            output_formatter: OutputFormatter instance for consistent output
        """
        self.output = output_formatter

    def init_service_id(self) -> None:
        """Initialize ServiceID for ansible-base."""
        try:
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

    def init_system_tasks(self, options: Dict[str, Any]) -> None:
        """
        Initialize system tasks.

        Args:
            options: Dictionary containing initialization options
        """
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
            self._handle_dry_run()
            return

        # Execute the initialization
        self._execute_initialization(create_system_tasks)

    def _handle_dry_run(self) -> None:
        """Handle dry run mode for system tasks initialization."""
        self.output.warning("🔧 System Tasks Initialization (DRY RUN)")
        self.output.write_separator()
        self.output.write("📝 This is a dry run - no changes will be made")
        self.output.write("")
        self._list_system_tasks()

    def _execute_initialization(self, create_system_tasks) -> None:
        """Execute the actual system tasks initialization."""
        self.output.success("🔧 System Tasks Initialization")
        self.output.write_separator()

        try:
            start_time = time.time()
            results = create_system_tasks()
            elapsed_time = time.time() - start_time

            self._display_results(results, elapsed_time)
        except Exception as e:
            raise CommandError(f"❌ Failed to initialize system tasks: {e}") from e

    def _display_results(self, results: Dict[str, Any], elapsed_time: float) -> None:
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

    def _display_task_details(self, results: Dict[str, Any]) -> None:
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

    def _list_system_tasks(self) -> None:
        """List current system tasks."""
        try:
            system_tasks = Task.objects.filter(is_system_task=True).order_by("created")

            if not system_tasks.exists():
                self.output.write("📭 No system tasks found")
                return

            self.output.write("📋 Current System Tasks")
            self.output.write_separator()

            # Group tasks by category
            categories = self._categorize_tasks(system_tasks)

            # Display tasks by category
            total_tasks = 0
            category_names = []

            for category, tasks in categories.items():
                self.output.write(f"\n🏷️  {category} ({len(tasks)} tasks)")
                self.output.write_separator("-", 40)

                for task in tasks:
                    self._display_task_info(task)

                total_tasks += len(tasks)
                category_names.append(category.lower())

            self.output.write_separator()
            self.output.write(f"📊 Total: {total_tasks} system tasks")
            self.output.write(f"📂 Categories: {', '.join(category_names)}")

        except Exception as e:
            self.output.error(f"❌ Failed to list system tasks: {e}")

    def _categorize_tasks(self, tasks) -> Dict[str, list]:
        """Categorize tasks by function name."""
        categories = {}
        for task in tasks:
            if "cleanup" in task.function_name:
                category = "MAINTENANCE"
            elif "collect" in task.function_name:
                category = "METRICS"
            else:
                category = "OTHER"

            if category not in categories:
                categories[category] = []
            categories[category].append(task)

        return categories

    def _display_task_info(self, task: Task) -> None:
        """Display information for a single task."""
        status_icon = "⏳" if task.status == "pending" else "✅" if task.status == "completed" else "❌"
        recurring_icon = "🔄" if task.is_recurring else "➡️"

        self.output.write(f"  {status_icon} {recurring_icon} {task.name}")
        self.output.write(f"    Function: {task.function_name}")
        if task.cron_expression:
            self.output.write(f"    Schedule: {task.cron_expression}")
        self.output.write(f"    Priority: {task.priority} | Status: {task.status}")
        self.output.write("")
