#!/usr/bin/env python
"""
Example script showing how to create and chain tasks using the new database-driven task system.

Run this script with: python manage.py shell < examples/create_sample_tasks.py
Or: python manage.py shell --command="exec(open('examples/create_sample_tasks.py').read())"
"""

from datetime import timedelta

from django.utils import timezone

from apps.tasks.models import Task, TaskChain, TaskChainMembership, TaskDependency

# For now, create tasks without user ownership to avoid DAB permission issues

# Create individual tasks

# Task 1: Data cleanup (immediate)
cleanup_task = Task.objects.create(
    name="Daily Data Cleanup", function_name="cleanup_old_data", task_data={"days_old": 7}, priority=2
)

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

# Task 3: User data processing (depends on cleanup)
user_processing_task = Task.objects.create(
    name="Process User Data",
    function_name="process_user_data",
    task_data={"user_id": 1, "operation": "validate"},
    priority=3,
)

# Task 4: Scheduled task for tomorrow
tomorrow = timezone.now() + timedelta(days=1)
scheduled_task = Task.objects.create(
    name="Tomorrow's Maintenance",
    function_name="cleanup_old_data",
    task_data={"days_old": 30},
    scheduled_time=tomorrow,
    priority=1,
)

# Task 5: Recurring task (daily at 2 AM)
recurring_task = Task.objects.create(
    name="Daily Health Check",
    function_name="cleanup_old_data",
    task_data={"days_old": 1},
    cron_expression="0 2 * * *",  # Daily at 2 AM
    is_recurring=True,
    priority=2,
)


# Create dependencies (task chains)
# Notification depends on cleanup completion
dep1 = TaskDependency.objects.create(
    dependent_task=notification_task, prerequisite_task=cleanup_task, required_status="completed"
)

# User processing depends on cleanup completion
dep2 = TaskDependency.objects.create(
    dependent_task=user_processing_task, prerequisite_task=cleanup_task, required_status="completed"
)


# Create a named task chain for the workflow
workflow_chain = TaskChain.objects.create(name="Daily Maintenance Workflow")

# Add tasks to the chain in order
TaskChainMembership.objects.create(chain=workflow_chain, task=cleanup_task, order=1)
TaskChainMembership.objects.create(chain=workflow_chain, task=notification_task, order=2)
TaskChainMembership.objects.create(chain=workflow_chain, task=user_processing_task, order=3)


ready_tasks = [task for task in Task.objects.filter(status="pending") if task.is_ready_to_run()]
for _task in ready_tasks:
    pass
