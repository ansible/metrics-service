# Database-Driven Task System

This implementation provides a comprehensive database-driven task scheduling system with task chaining capabilities, replacing the static `SCHEDULED_TASKS` configuration.

## Features

- **Database-stored tasks**: All tasks are stored in the database for persistence and management
- **Task chaining**: Create dependencies between tasks for complex workflows
- **Flexible scheduling**: Support for immediate, scheduled, and recurring (cron-based) tasks
- **Priority management**: Task prioritization for execution order
- **Retry logic**: Automatic retry with configurable max attempts
- **Execution tracking**: Detailed history of task executions
- **Chain management**: Named task chains for complex workflows
- **Django admin integration**: Full admin interface for task management
- **Management commands**: CLI tools for task operations

## Database Models

### Task

- **Purpose**: Main task definition and execution tracking
- **Key fields**: `name`, `function_name`, `task_data`, `status`, `scheduled_time`, `cron_expression`
- **States**: `pending`, `running`, `completed`, `failed`, `cancelled`, `waiting_for_dependencies`

### TaskDependency

- **Purpose**: Define dependencies between tasks for chaining
- **Key fields**: `dependent_task`, `prerequisite_task`, `required_status`

### TaskExecution

- **Purpose**: Track individual task execution history
- **Key fields**: `task`, `status`, `started_at`, `completed_at`, `worker_id`, `execution_time_seconds`

### TaskChain

- **Purpose**: Named collections of tasks for complex workflows
- **Key fields**: `name`, `description`, `is_active`

### TaskChainMembership

- **Purpose**: Define task order within chains
- **Key fields**: `chain`, `task`, `order`

## Usage Examples

### 1. Create a Simple Task

```python
from apps.core.models import Task

task = Task.objects.create(
    name="Daily Cleanup",
    function_name="cleanup_old_data",
    task_data={"days_old": 30},
    priority=2
)
```

### 2. Create a Scheduled Task

```python
from django.utils import timezone
from datetime import timedelta

scheduled_time = timezone.now() + timedelta(hours=2)
task = Task.objects.create(
    name="Scheduled Maintenance",
    function_name="cleanup_old_data",
    task_data={"days_old": 7},
    scheduled_time=scheduled_time
)
```

### 3. Create a Recurring Task

```python
task = Task.objects.create(
    name="Daily Health Check",
    function_name="cleanup_old_data",
    task_data={"days_old": 1},
    cron_expression="0 2 * * *",  # Daily at 2 AM
    is_recurring=True
)
```

### 4. Create Task Dependencies (Chaining)

```python
from apps.core.models import TaskDependency

# Create two tasks
task1 = Task.objects.create(name="Backup Data", function_name="cleanup_old_data")
task2 = Task.objects.create(name="Send Report", function_name="send_notification_email")

# Make task2 depend on task1 completion
TaskDependency.objects.create(
    dependent_task=task2,
    prerequisite_task=task1,
    required_status="completed"
)
```

### 5. Create a Task Chain

```python
from apps.core.models import TaskChain, TaskChainMembership

# Create a workflow chain
workflow = TaskChain.objects.create(
    name="Daily Maintenance Workflow",
    description="Complete daily maintenance with notifications"
)

# Add tasks in order
TaskChainMembership.objects.create(chain=workflow, task=task1, order=1)
TaskChainMembership.objects.create(chain=workflow, task=task2, order=2)
```

## Management Commands

### 1. Task Management Command

```bash
# Create a new task
python manage.py manage_tasks create \
    --name "Cleanup Task" \
    --function cleanup_old_data \
    --data '{"days_old": 30}' \
    --priority 2

# List all tasks
python manage.py manage_tasks list

# Show task details
python manage.py manage_tasks show 1

# Cancel a task
python manage.py manage_tasks cancel 1

# Retry a failed task
python manage.py manage_tasks retry 1

# Add task dependency
python manage.py manage_tasks add-dependency --dependent 2 --prerequisite 1

# Create a task chain
python manage.py manage_tasks create-chain \
    --name "My Workflow" \
    --tasks "1,2,3"

# Clean up old completed tasks
python manage.py manage_tasks cleanup --days 30
```

### 2. Task Scheduler Command

```bash
# Start the task scheduler (polls database for ready tasks)
python manage.py run_task_scheduler --poll-interval 30

# Start with custom settings
python manage.py run_task_scheduler \
    --poll-interval 15 \
    --log-level DEBUG
```

### 3. Enhanced Dispatcher Command

```bash
# Start dispatcher with integrated task scheduler
python manage.py run_dispatcher

# The dispatcher now automatically:
# - Starts the task scheduler in a background thread
# - Processes both database tasks and legacy scheduled tasks
# - Handles task dependencies and chaining
```

## Django Admin Integration

The system includes comprehensive Django admin integration:

1. **Task Admin**: View, edit, and manage tasks with colored status indicators
2. **Task Dependency Admin**: Manage task relationships
3. **Task Execution Admin**: View execution history and performance metrics
4. **Task Chain Admin**: Manage workflow chains
5. **Admin Actions**: Bulk cancel, retry, and reset tasks

## API Integration

Tasks integrate with the existing dispatcherd system:

- All database tasks use the `execute_db_task` function
- Automatic dependency resolution and chaining
- Seamless integration with existing task functions
- Backward compatibility with `SCHEDULED_TASKS`

## Running the System

### Option 1: Integrated Dispatcher (Recommended)

```bash
# Starts both dispatcherd and task scheduler
python manage.py run_dispatcher
```

### Option 2: Separate Services

```bash
# Terminal 1: Start task scheduler
python manage.py run_task_scheduler

# Terminal 2: Start dispatcher
python manage.py run_dispatcher
```

### Using Docker/Podman

```bash
# Build and run with database
podman compose up -d

# Create sample tasks
podman compose run --rm --entrypoint="" metrics-service \
    python manage.py shell --command="exec(open('examples/create_sample_tasks.py').read())"

# Start the enhanced dispatcher
podman compose exec metrics-service python manage.py run_dispatcher
```

## Migration from Static Tasks

The system maintains backward compatibility with the existing `SCHEDULED_TASKS` configuration. To migrate:

1. **Keep existing tasks**: Current `SCHEDULED_TASKS` continue to work
2. **Gradually migrate**: Create database equivalents of static tasks
3. **Remove static config**: Once database tasks are verified, remove from `SCHEDULED_TASKS`

Example migration:

```python
# Old static configuration
SCHEDULED_TASKS = {
    "daily_cleanup": {
        "function": "cleanup_old_data",
        "schedule": 86400,
        "data": {"days_old": 30},
    },
}

# New database task
Task.objects.create(
    name="Daily Cleanup",
    function_name="cleanup_old_data",
    task_data={"days_old": 30},
    cron_expression="0 0 * * *",  # Daily at midnight
    is_recurring=True
)
```

## Task Function Requirements

Task functions must follow the existing pattern:

```python
def my_task_function(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Custom task function.

    Args:
        data: Task data from the database

    Returns:
        Dict with 'status' key ('success' or 'error') and optional result data
    """
    try:
        # Your task logic here
        result = perform_work(data)
        return {"status": "success", "result": result}
    except Exception as e:
        return {"status": "error", "error": str(e)}

# Register the function
TASK_FUNCTIONS = {
    # ... existing functions ...
    "my_task_function": my_task_function,
}
```

## Monitoring and Debugging

### Task Status Monitoring

```python
# Check task status
from apps.core.models import Task

pending_tasks = Task.objects.filter(status='pending')
running_tasks = Task.objects.filter(status='running')
failed_tasks = Task.objects.filter(status='failed')

# Check ready tasks
ready_tasks = [t for t in pending_tasks if t.is_ready_to_run()]
```

### Execution History

```python
from apps.core.models import TaskExecution

# Get execution history for a task
executions = TaskExecution.objects.filter(task_id=1).order_by('-started_at')

# Check average execution time
avg_time = executions.aggregate(avg_time=models.Avg('execution_time_seconds'))
```

### Dependency Chains

```python
# Find all dependencies for a task
task = Task.objects.get(id=1)
dependencies = task.dependencies.all()
dependents = task.dependents.all()

# Check if a task is ready to run
if task.is_ready_to_run():
    print("Task is ready!")
```

## Best Practices

1. **Use meaningful names**: Task names should clearly describe their purpose
2. **Set appropriate priorities**: Use priority levels to control execution order
3. **Handle errors gracefully**: Task functions should return proper error status
4. **Monitor execution times**: Use TaskExecution data to optimize performance
5. **Clean up old data**: Regularly clean up completed task executions
6. **Test dependencies**: Verify task chains work as expected
7. **Use recurring tasks sparingly**: Prefer event-driven tasks when possible

## Troubleshooting

### Common Issues

1. **Tasks stuck in running state**: Check for timeouts and worker crashes
2. **Dependencies not triggering**: Verify prerequisite task status and required_status
3. **Cron expressions not working**: Ensure `croniter` package is installed
4. **Permissions errors**: Check task ownership and user permissions

### Debug Commands

```bash
# Check system status
python manage.py manage_tasks list --status running

# View task details
python manage.py manage_tasks show <task_id>

# Clean up stale tasks
python manage.py manage_tasks cleanup --dry-run
```
