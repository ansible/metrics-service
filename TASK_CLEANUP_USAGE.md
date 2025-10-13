# Task Cleanup Usage Guide

The `cleanup_old_tasks` function automatically removes completed and failed tasks that are older than a specified number of days (default: 5 days).

🔄 **IMPORTANT**: Recurring tasks are automatically preserved and will NOT be deleted, regardless of their age, to ensure scheduled tasks continue to function properly.

## Function: `cleanup_old_tasks`

### Parameters

- **`days_old`** (int, default: 5): Number of days old tasks should be to qualify for cleanup
- **`dry_run`** (bool, default: False): If True, only count tasks that would be deleted without actually deleting them
- **`include_executions`** (bool, default: True): Also cleanup related TaskExecution records
- **`preserve_recurring`** (bool, default: True): If True, exclude recurring tasks from cleanup to preserve scheduled tasks

### Usage Examples

#### 1. Basic Cleanup (5 days old)
```python
# Create a task to clean up tasks older than 5 days
{
  "name": "Daily Task Cleanup",
  "function_name": "cleanup_old_tasks",
  "task_data": {}
}
```

#### 2. Custom Days with Dry Run
```python
# Test what would be deleted (7 days old)
{
  "name": "Test Cleanup - 7 Days",
  "function_name": "cleanup_old_tasks",
  "task_data": {
    "days_old": 7,
    "dry_run": true
  }
}
```

#### 3. Aggressive Cleanup (Keep only 3 days)
```python
# Clean up tasks older than 3 days
{
  "name": "Aggressive Cleanup",
  "function_name": "cleanup_old_tasks",
  "task_data": {
    "days_old": 3,
    "include_executions": true
  }
}
```

#### 4. Conservative Cleanup (Keep executions)
```python
# Only delete tasks, keep execution history
{
  "name": "Conservative Cleanup",
  "function_name": "cleanup_old_tasks",
  "task_data": {
    "days_old": 10,
    "include_executions": false
  }
}
```

#### 5. Advanced: Include Recurring Tasks (Not Recommended)
```python
# WARNING: This will delete recurring tasks too!
# Only use if you want to completely reset all tasks
{
  "name": "Nuclear Cleanup",
  "function_name": "cleanup_old_tasks",
  "task_data": {
    "days_old": 30,
    "preserve_recurring": false
  }
}
```

### Scheduled Cleanup

To run cleanup automatically, create a recurring task:

```python
{
  "name": "Daily Task Cleanup",
  "function_name": "cleanup_old_tasks",
  "task_data": {
    "days_old": 5
  },
  "cron_expression": "0 2 * * *",  # Daily at 2 AM
  "is_recurring": true
}
```

### Return Data

The function returns detailed statistics:

```json
{
  "status": "success",
  "data": {
    "days_old": 5,
    "cutoff_date": "2025-10-03T13:18:57.496938+00:00",
    "dry_run": false,
    "include_executions": true,
    "preserve_recurring": true,
    "tasks_found": 15,
    "executions_found": 23,
    "tasks_deleted": 15,
    "executions_deleted": 23
  }
}
```

### What Gets Cleaned Up

The cleanup function targets:

1. **Tasks** with status `completed` or `failed`
2. **Completion time** older than the specified days (uses `completed_at` field)
3. **Fallback** to `modified` date for tasks without `completed_at`
4. **Related executions** (if `include_executions` is True)

### 🛡️ What Gets PROTECTED

The cleanup function automatically preserves:

1. **Recurring tasks** (default behavior) - Tasks with `is_recurring=True` are never deleted
2. **Pending/running tasks** - Only completed/failed tasks are considered
3. **Recent tasks** - Tasks newer than the specified age threshold

### Safety Features

- **Recurring task protection**: Automatically preserves scheduled tasks by default
- **Dry run mode**: Test what would be deleted without actually deleting
- **Status filtering**: Only targets completed/failed tasks (never pending/running)
- **Date validation**: Uses proper timezone-aware date comparisons
- **Cascade handling**: Properly handles foreign key relationships
- **Detailed logging**: Provides comprehensive feedback on operations
- **Configurable protection**: Option to override recurring task protection if needed

### Recommended Schedule

- **Development**: Run weekly with 7-day retention
- **Production**: Run daily with 5-day retention
- **High-volume**: Run daily with 3-day retention

Always test with `dry_run: true` first to understand the impact.