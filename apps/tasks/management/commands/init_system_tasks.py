"""
Django management command to initialize system-defined tasks.

This command creates or updates system tasks like cleanup and metrics collection
that should always be present in the system.
"""

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.tasks.tasks import create_system_tasks, get_system_task_info


class Command(BaseCommand):
    """
    Management command to initialize system tasks.

    This command ensures that essential system tasks are created and properly
    configured. It should be run after database migrations and can be run
    multiple times safely (it will update existing tasks if needed).
    """

    help = "Initialize system-defined tasks (cleanup, metrics collection, etc.)"

    def add_arguments(self, parser):
        """Add command line arguments."""
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be created/updated without making changes",
        )
        parser.add_argument(
            "--list",
            action="store_true",
            help="List existing system tasks and their status",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Force update of all system tasks even if they appear unchanged",
        )

    def handle(self, *args, **options):
        """Execute the command."""
        self.stdout.write(self.style.SUCCESS("🔧 System Tasks Initialization"))
        self.stdout.write("=" * 50)

        if options["list"]:
            self.list_system_tasks()
            return

        if options["dry_run"]:
            self.stdout.write(self.style.WARNING("🔍 DRY RUN MODE - No changes will be made"))

        try:
            # Get current time for logging
            start_time = timezone.now()

            # Create/update system tasks
            results = create_system_tasks()

            if "error" in results:
                raise CommandError(f"Error creating system tasks: {results['error']}")

            # Display results
            self.display_results(results, options["dry_run"])

            # Show summary
            total_tasks = results["created"] + results["updated"] + results["skipped"]
            self.stdout.write("\n" + "=" * 50)
            self.stdout.write(
                self.style.SUCCESS(
                    f"✅ Processed {total_tasks} system tasks in {(timezone.now() - start_time).total_seconds():.2f} seconds"
                )
            )

            if not options["dry_run"]:
                self.stdout.write(
                    self.style.SUCCESS("💡 Run 'python manage.py init_system_tasks --list' to see current status")
                )

        except Exception as e:
            raise CommandError(f"Failed to initialize system tasks: {str(e)}")

    def display_results(self, results, is_dry_run):
        """Display the results of task creation/update."""
        self.stdout.write("\n📊 Results:")

        if results["created"] > 0:
            self.stdout.write(self.style.SUCCESS(f"  ✅ Created: {results['created']} tasks"))

        if results["updated"] > 0:
            self.stdout.write(self.style.WARNING(f"  🔄 Updated: {results['updated']} tasks"))

        if results["skipped"] > 0:
            self.stdout.write(f"  ⏭️  Skipped: {results['skipped']} tasks (no changes needed)")

        # Show detailed task list
        if results["tasks"]:
            self.stdout.write("\n📋 Task Details:")
            for task_info in results["tasks"]:
                if task_info.startswith("Created:"):
                    self.stdout.write(f"  {self.style.SUCCESS('✅')} {task_info}")
                elif task_info.startswith("Updated:"):
                    self.stdout.write(f"  {self.style.WARNING('🔄')} {task_info}")
                elif task_info.startswith("Skipped:"):
                    self.stdout.write(f"  ⏭️  {task_info}")
                elif task_info.startswith("Error:"):
                    self.stdout.write(f"  {self.style.ERROR('❌')} {task_info}")
                else:
                    self.stdout.write(f"  ℹ️  {task_info}")

    def list_system_tasks(self):
        """List existing system tasks and their status."""
        self.stdout.write("📋 Current System Tasks\n")

        try:
            info = get_system_task_info()

            if "error" in info:
                self.stdout.write(self.style.ERROR(f"Error getting system tasks: {info['error']}"))
                return

            system_tasks = info["system_tasks"]

            if not system_tasks:
                self.stdout.write(self.style.WARNING("⚠️  No system tasks found. Run without --list to create them."))
                return

            # Group by category
            categories = {}
            for task in system_tasks:
                category = task["category"]
                if category not in categories:
                    categories[category] = []
                categories[category].append(task)

            # Display by category
            for category, tasks in sorted(categories.items()):
                self.stdout.write(f"\n🏷️  {category.upper()} ({len(tasks)} tasks)")
                self.stdout.write("-" * 40)

                for task in tasks:
                    status_icon = self.get_status_icon(task["status"])
                    recurring_icon = "🔄" if task["is_recurring"] else "⚡"

                    self.stdout.write(f"  {status_icon} {recurring_icon} {task['name']}")
                    self.stdout.write(f"    Function: {task['function_name']}")
                    self.stdout.write(f"    Schedule: {task['cron_expression'] or 'Manual'}")
                    self.stdout.write(f"    Priority: {task['priority']} | Status: {task['status']}")
                    if task["last_run"]:
                        self.stdout.write(f"    Last run: {task['last_run']}")
                    self.stdout.write("")

            # Summary
            self.stdout.write("=" * 50)
            self.stdout.write(self.style.SUCCESS(f"📊 Total: {info['total_count']} system tasks"))
            self.stdout.write(f"📂 Categories: {', '.join(info['categories'])}")

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error listing system tasks: {str(e)}"))

    def get_status_icon(self, status):
        """Get appropriate icon for task status."""
        status_icons = {
            "pending": "⏳",
            "running": "🏃",
            "completed": "✅",
            "failed": "❌",
            "cancelled": "🚫",
            "waiting_for_dependencies": "⏸️",
        }
        return status_icons.get(status, "❓")
