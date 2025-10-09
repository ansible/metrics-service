"""
Django management command to process pending database tasks.

This command finds all pending tasks in the database and submits them to dispatcherd for processing.
"""

import logging
from django.core.management.base import BaseCommand
from apps.tasks.models import Task
from apps.tasks.tasks import submit_task_to_dispatcher

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """Management command to process pending database tasks."""

    help = "Process all pending tasks in the database by submitting them to dispatcherd"

    def add_arguments(self, parser):
        """Add command line arguments."""
        parser.add_argument(
            "--limit",
            type=int,
            default=50,
            help="Maximum number of tasks to process (default: 50)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be processed without actually submitting tasks",
        )

    def handle(self, *args, **options):
        """Handle the command execution."""
        try:
            # Get pending tasks
            pending_tasks = Task.objects.filter(status="pending").order_by("created")[: options["limit"]]
            
            if not pending_tasks:
                self.stdout.write(self.style.SUCCESS("No pending tasks found"))
                return
            
            self.stdout.write(f"Found {len(pending_tasks)} pending tasks")
            
            if options["dry_run"]:
                self.stdout.write(self.style.WARNING("DRY RUN - No tasks will be submitted"))
                for task in pending_tasks:
                    ready = task.is_ready_to_run()
                    status = "✓ Ready" if ready else "⏳ Not ready"
                    self.stdout.write(f"  {status} - {task.id}: {task.name} ({task.function_name})")
                return
            
            # Process ready tasks
            processed = 0
            skipped = 0
            errors = 0
            
            for task in pending_tasks:
                if not task.is_ready_to_run():
                    self.stdout.write(f"⏭️  Skipped {task.id}: {task.name} (not ready)")
                    skipped += 1
                    continue
                
                try:
                    submit_task_to_dispatcher(task)
                    self.stdout.write(f"✅ Submitted {task.id}: {task.name}")
                    processed += 1
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"❌ Failed {task.id}: {task.name} - {e}"))
                    errors += 1
            
            # Summary
            self.stdout.write("")
            self.stdout.write(self.style.SUCCESS(f"Summary:"))
            self.stdout.write(f"  ✅ Processed: {processed}")
            self.stdout.write(f"  ⏭️  Skipped: {skipped}")
            self.stdout.write(f"  ❌ Errors: {errors}")
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Failed to process pending tasks: {e}"))
            raise