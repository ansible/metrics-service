#!/usr/bin/env python
"""
Example script showing how to create and chain tasks using the new database-driven task system.

Run this script with: python manage.py shell < examples/create_sample_tasks.py
Or: python manage.py shell --command="exec(open('examples/create_sample_tasks.py').read())"
"""

from datetime import timedelta

from django.utils import timezone

from apps.core.models import Task, TaskChain, TaskChainMembership, TaskDependency

print("=== Creating Sample Tasks ===")

# For now, create tasks without user ownership to avoid DAB permission issues
print("Creating tasks without user ownership for now")

# Create individual tasks
print("\n--- Creating Individual Tasks ---")

# Task 1: Data cleanup (immediate)
cleanup_task = Task.objects.create(
    name="Daily Data Cleanup", function_name="cleanup_old_data", task_data={"days_old": 7}, priority=2
)
print(f"Created task: {cleanup_task.name} (ID: {cleanup_task.id})")

# Task 2: Send notification (depends on cleanup)
notification_task = Task.objects.create(
    name="Send Cleanup Report",
    function_name="send_notification_email",
    task_data={
        "recipient": "admin@example.com",
        "subject": "Cleanup Report",
        "message": "Daily cleanup has completed successfully.",
    },
    priority=2,
)
print(f"Created task: {notification_task.name} (ID: {notification_task.id})")

# Task 3: User data processing (depends on cleanup)
user_processing_task = Task.objects.create(
    name="Process User Data",
    function_name="process_user_data",
    task_data={"user_id": 1, "operation": "validate"},
    priority=3,
)
print(f"Created task: {user_processing_task.name} (ID: {user_processing_task.id})")

# Task 4: Scheduled task for tomorrow
tomorrow = timezone.now() + timedelta(days=1)
scheduled_task = Task.objects.create(
    name="Tomorrow's Maintenance",
    function_name="cleanup_old_data",
    task_data={"days_old": 30},
    scheduled_time=tomorrow,
    priority=1,
)
print(f"Created scheduled task: {scheduled_task.name} (ID: {scheduled_task.id}) for {tomorrow}")

# Task 5: Recurring task (daily at 2 AM)
recurring_task = Task.objects.create(
    name="Daily Health Check",
    function_name="cleanup_old_data",
    task_data={"days_old": 1},
    cron_expression="0 2 * * *",  # Daily at 2 AM
    is_recurring=True,
    priority=2,
)
print(f"Created recurring task: {recurring_task.name} (ID: {recurring_task.id})")

print("\n--- Creating Task Dependencies ---")

# Create dependencies (task chains)
# Notification depends on cleanup completion
dep1 = TaskDependency.objects.create(
    dependent_task=notification_task, prerequisite_task=cleanup_task, required_status="completed"
)
print(f"Created dependency: {notification_task.name} depends on {cleanup_task.name}")

# User processing depends on cleanup completion
dep2 = TaskDependency.objects.create(
    dependent_task=user_processing_task, prerequisite_task=cleanup_task, required_status="completed"
)
print(f"Created dependency: {user_processing_task.name} depends on {cleanup_task.name}")

print("\n--- Creating Task Chain ---")

# Create a named task chain for the workflow
workflow_chain = TaskChain.objects.create(name="Daily Maintenance Workflow")

# Add tasks to the chain in order
TaskChainMembership.objects.create(chain=workflow_chain, task=cleanup_task, order=1)
TaskChainMembership.objects.create(chain=workflow_chain, task=notification_task, order=2)
TaskChainMembership.objects.create(chain=workflow_chain, task=user_processing_task, order=3)

print(f"Created task chain: {workflow_chain.name} with {workflow_chain.tasks.count()} tasks")

print("\n--- Task Summary ---")
print(f"Total tasks created: {Task.objects.count()}")
print(f"Total dependencies: {TaskDependency.objects.count()}")
print(f"Total chains: {TaskChain.objects.count()}")

print("\n--- Ready Tasks ---")
ready_tasks = [task for task in Task.objects.filter(status="pending") if task.is_ready_to_run()]
print(f"Tasks ready to run: {len(ready_tasks)}")
for task in ready_tasks:
    print(f"  - {task.name} (Priority: {task.get_priority_display()})")

print("\n=== Sample Tasks Created Successfully ===")
print("\nTo manage these tasks, you can:")
print("1. Use the Django admin interface")
print("2. Use the manage_tasks command:")
print("   python manage.py manage_tasks list")
print("   python manage.py manage_tasks show <task_id>")
print("3. Start the task scheduler:")
print("   python manage.py run_task_scheduler")
print("4. Start the dispatcher (includes task scheduler):")
print("   python manage.py run_dispatcher")
