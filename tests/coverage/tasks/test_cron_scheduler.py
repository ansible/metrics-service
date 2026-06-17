"""
Unit tests for apps/tasks/cron_scheduler.py.
Targets 13.78% → ~90% coverage.
"""

from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone


# ---------------------------------------------------------------------------
# _inject_dispatch_timestamps
# ---------------------------------------------------------------------------
@pytest.mark.unit
def test_inject_timestamps_hourly_pins_previous_hour():
    from apps.tasks.cron_scheduler import _inject_dispatch_timestamps

    result = _inject_dispatch_timestamps("collect_hourly_metrics", {})
    assert "hour_timestamp" in result
    # The pinned timestamp should be on the hour boundary
    from apps.tasks.utils import parse_datetime_string

    dt = parse_datetime_string(result["hour_timestamp"])
    assert dt is not None
    assert dt.minute == 0
    assert dt.second == 0


@pytest.mark.unit
def test_inject_timestamps_snapshot_sets_collection_timestamp():
    from apps.tasks.cron_scheduler import _inject_dispatch_timestamps

    result = _inject_dispatch_timestamps("collect_snapshot_metrics", {})
    assert "collection_timestamp" in result


@pytest.mark.unit
def test_inject_timestamps_daily_sets_hour_timestamp():
    from apps.tasks.cron_scheduler import _inject_dispatch_timestamps

    result = _inject_dispatch_timestamps("collect_daily_metrics", {})
    assert "hour_timestamp" in result
    from apps.tasks.utils import parse_datetime_string

    dt = parse_datetime_string(result["hour_timestamp"])
    assert dt.hour == 0


@pytest.mark.unit
def test_inject_timestamps_does_not_overwrite_existing():
    from apps.tasks.cron_scheduler import _inject_dispatch_timestamps

    existing_ts = "2024-01-01T10:00:00+00:00"
    task_data = {"hour_timestamp": existing_ts}
    result = _inject_dispatch_timestamps("collect_hourly_metrics", task_data)
    assert result["hour_timestamp"] == existing_ts


@pytest.mark.unit
def test_inject_timestamps_unknown_function_unchanged():
    from apps.tasks.cron_scheduler import _inject_dispatch_timestamps

    task_data = {"collector_type": "foo"}
    result = _inject_dispatch_timestamps("some_other_function", task_data)
    assert result == {"collector_type": "foo"}


@pytest.mark.unit
def test_inject_timestamps_returns_copy():
    from apps.tasks.cron_scheduler import _inject_dispatch_timestamps

    original = {}
    result = _inject_dispatch_timestamps("collect_hourly_metrics", original)
    assert result is not original


# ---------------------------------------------------------------------------
# UnifiedTaskScheduler — start / stop
# ---------------------------------------------------------------------------
@pytest.mark.unit
def test_scheduler_start_and_stop(mock_apscheduler):
    import apps.tasks.cron_scheduler as cs

    # Reset the global singleton
    cs._scheduler_instance = None

    with patch.object(cs.UnifiedTaskScheduler, "_sync_database_tasks"):
        scheduler = cs.UnifiedTaskScheduler()
        scheduler.start()

    assert scheduler.running is True
    scheduler.scheduler = mock_apscheduler
    scheduler.stop()
    assert scheduler.running is False


@pytest.mark.unit
def test_scheduler_start_idempotent(mock_apscheduler):
    import apps.tasks.cron_scheduler as cs

    with patch.object(cs.UnifiedTaskScheduler, "_sync_database_tasks"):
        scheduler = cs.UnifiedTaskScheduler()
        scheduler.start()
        # Second call should be a no-op
        scheduler.start()

    # scheduler.start() on the mock should have been called only once
    mock_apscheduler.start.assert_called_once()
    scheduler.scheduler = mock_apscheduler
    scheduler.stop()


@pytest.mark.unit
def test_scheduler_stop_when_not_running(mock_apscheduler):
    import apps.tasks.cron_scheduler as cs

    scheduler = cs.UnifiedTaskScheduler()
    scheduler.scheduler = mock_apscheduler
    # Stop without starting should be a no-op
    scheduler.stop()
    mock_apscheduler.shutdown.assert_not_called()


# ---------------------------------------------------------------------------
# _task_feature_flag_enabled
# ---------------------------------------------------------------------------
@pytest.mark.unit
@pytest.mark.django_db
def test_task_feature_flag_enabled_no_flag(user):
    import apps.tasks.cron_scheduler as cs
    from apps.tasks.models import Task

    task = Task.objects.create(name="t", function_name="hello_world", task_data={}, created_by=user)
    scheduler = cs.UnifiedTaskScheduler()
    assert scheduler._task_feature_flag_enabled(task) is True


@pytest.mark.unit
@pytest.mark.django_db
def test_task_feature_flag_enabled_flag_on(user):
    import apps.tasks.cron_scheduler as cs
    from apps.dynamic_settings.models import Setting
    from apps.tasks.models import Task

    Setting.objects.get_or_create(setting_key="SCHED_FLAG_ON", defaults={"current_value": "true"})
    task = Task.objects.create(
        name="t", function_name="hello_world", task_data={"_feature_flag": "SCHED_FLAG_ON"}, created_by=user
    )
    scheduler = cs.UnifiedTaskScheduler()
    assert scheduler._task_feature_flag_enabled(task) is True


@pytest.mark.unit
@pytest.mark.django_db
def test_task_feature_flag_enabled_flag_off(user):
    import apps.tasks.cron_scheduler as cs
    from apps.dynamic_settings.models import Setting
    from apps.tasks.models import Task

    Setting.objects.get_or_create(setting_key="SCHED_FLAG_OFF", defaults={"current_value": "false"})
    task = Task.objects.create(
        name="t2", function_name="hello_world", task_data={"_feature_flag": "SCHED_FLAG_OFF"}, created_by=user
    )
    scheduler = cs.UnifiedTaskScheduler()
    assert scheduler._task_feature_flag_enabled(task) is False


# ---------------------------------------------------------------------------
# _add_database_recurring_task
# ---------------------------------------------------------------------------
@pytest.mark.unit
@pytest.mark.django_db
def test_add_recurring_task_registers_job(user, mock_apscheduler):
    import apps.tasks.cron_scheduler as cs
    from apps.tasks.models import Task

    task = Task.objects.create(
        name="rec", function_name="hello_world", cron_expression="0 * * * *", task_data={}, created_by=user
    )
    scheduler = cs.UnifiedTaskScheduler()
    scheduler.scheduler = mock_apscheduler
    scheduler._add_database_recurring_task(task)

    mock_apscheduler.add_job.assert_called_once()
    assert task.id in scheduler._db_task_jobs


@pytest.mark.unit
@pytest.mark.django_db
def test_add_recurring_task_skips_if_already_tracked(user, mock_apscheduler):
    import apps.tasks.cron_scheduler as cs
    from apps.tasks.models import Task

    task = Task.objects.create(
        name="rec2", function_name="hello_world", cron_expression="0 * * * *", task_data={}, created_by=user
    )
    scheduler = cs.UnifiedTaskScheduler()
    scheduler.scheduler = mock_apscheduler
    scheduler._db_task_jobs[task.id] = "already_there"

    scheduler._add_database_recurring_task(task)
    mock_apscheduler.add_job.assert_not_called()


# ---------------------------------------------------------------------------
# _add_database_scheduled_task
# ---------------------------------------------------------------------------
@pytest.mark.unit
@pytest.mark.django_db
def test_add_scheduled_task_future_registers_job(user, mock_apscheduler):
    import apps.tasks.cron_scheduler as cs
    from apps.tasks.models import Task

    future_time = timezone.now() + timedelta(hours=1)
    task = Task.objects.create(
        name="sched", function_name="hello_world", scheduled_time=future_time, task_data={}, created_by=user
    )
    scheduler = cs.UnifiedTaskScheduler()
    scheduler.scheduler = mock_apscheduler
    scheduler._add_database_scheduled_task(task)

    mock_apscheduler.add_job.assert_called_once()
    assert task.id in scheduler._db_task_jobs


@pytest.mark.unit
@pytest.mark.django_db
def test_add_scheduled_task_past_due_executes_immediately(user, mock_apscheduler):
    import apps.tasks.cron_scheduler as cs
    from apps.tasks.models import Task

    past_time = timezone.now() - timedelta(hours=2)
    task = Task.objects.create(
        name="past_sched", function_name="hello_world", scheduled_time=past_time, task_data={}, created_by=user
    )
    scheduler = cs.UnifiedTaskScheduler()
    scheduler.scheduler = mock_apscheduler

    with patch.object(scheduler, "_execute_database_task") as mock_execute:
        scheduler._add_database_scheduled_task(task)
        mock_execute.assert_called_once_with(task.id)


# ---------------------------------------------------------------------------
# _remove_database_task
# ---------------------------------------------------------------------------
@pytest.mark.unit
def test_remove_database_task_calls_remove_job(mock_apscheduler):
    import apps.tasks.cron_scheduler as cs

    scheduler = cs.UnifiedTaskScheduler()
    scheduler.scheduler = mock_apscheduler
    scheduler._db_task_jobs[42] = "job_id_42"

    scheduler._remove_database_task(42)

    mock_apscheduler.remove_job.assert_called_once_with("job_id_42")
    assert 42 not in scheduler._db_task_jobs


@pytest.mark.unit
def test_remove_database_task_not_tracked_is_noop(mock_apscheduler):
    import apps.tasks.cron_scheduler as cs

    scheduler = cs.UnifiedTaskScheduler()
    scheduler.scheduler = mock_apscheduler
    # Calling remove on a non-tracked ID should not raise
    scheduler._remove_database_task(999)
    mock_apscheduler.remove_job.assert_not_called()


# ---------------------------------------------------------------------------
# _execute_database_task — recurring creates child
# ---------------------------------------------------------------------------
@pytest.mark.unit
@pytest.mark.django_db
def test_execute_database_task_recurring_creates_child_task(user, mock_apscheduler, mock_dispatcherd_config):
    import apps.tasks.cron_scheduler as cs
    from apps.tasks.models import Task

    task = Task.objects.create(
        name="template",
        function_name="hello_world",
        cron_expression="0 * * * *",
        task_data={"_feature_flag": "METRICS_COLLECTION"},
        created_by=user,
        is_system_task=True,
    )

    scheduler = cs.UnifiedTaskScheduler()
    scheduler.scheduler = mock_apscheduler

    with (
        patch("apps.tasks.cron_scheduler.close_old_connections"),
        patch("apps.tasks.tasks_system.submit_task_to_dispatcher") as mock_submit,
        patch("apps.tasks.task_groups.get_feature_enabled_from_db", return_value=True),
    ):
        scheduler._execute_database_task(task.id)

    # A new (non-recurring) child task should be created
    child = Task.objects.exclude(id=task.id).filter(function_name="hello_world").first()
    assert child is not None
    assert child.cron_expression is None
    mock_submit.assert_called_once_with(child)


@pytest.mark.unit
@pytest.mark.django_db
def test_execute_database_task_not_found_removes_tracking(user, mock_apscheduler):
    import apps.tasks.cron_scheduler as cs

    scheduler = cs.UnifiedTaskScheduler()
    scheduler.scheduler = mock_apscheduler
    scheduler._db_task_jobs[9999] = "some_job"

    with patch("apps.tasks.cron_scheduler.close_old_connections"):
        scheduler._execute_database_task(9999)

    # Job should be removed from tracking
    assert 9999 not in scheduler._db_task_jobs


@pytest.mark.unit
@pytest.mark.django_db
def test_execute_database_task_cancelled_task_removed(user, mock_apscheduler):
    import apps.tasks.cron_scheduler as cs
    from apps.tasks.models import Task

    task = Task.objects.create(
        name="cancelled", function_name="hello_world", task_data={}, created_by=user, status="cancelled"
    )
    scheduler = cs.UnifiedTaskScheduler()
    scheduler.scheduler = mock_apscheduler
    scheduler._db_task_jobs[task.id] = "job_id"

    with (
        patch("apps.tasks.cron_scheduler.close_old_connections"),
        patch.object(scheduler, "_remove_database_task") as mock_remove,
    ):
        scheduler._execute_database_task(task.id)
        mock_remove.assert_called_once_with(task.id)


# ---------------------------------------------------------------------------
# _periodic_database_sync — stuck tasks
# ---------------------------------------------------------------------------
@pytest.mark.unit
@pytest.mark.django_db
def test_periodic_sync_fails_stuck_tasks(user, mock_apscheduler):
    import apps.tasks.cron_scheduler as cs
    from apps.tasks.models import Task, TaskExecution

    task = Task.objects.create(
        name="stuck", function_name="hello_world", task_data={}, created_by=user, status="running"
    )
    # Backdate started_at to trigger stuck detection
    started = timezone.now() - timedelta(
        seconds=cs.STUCK_TASK_TIMEOUT_SECONDS + cs.STUCK_TASK_TIMEOUT_PADDING_SECONDS + 1
    )
    Task.objects.filter(pk=task.pk).update(started_at=started)
    execution = TaskExecution.objects.create(task=task, status="running")

    scheduler = cs.UnifiedTaskScheduler()
    scheduler.scheduler = mock_apscheduler

    # _periodic_database_sync also calls Task.immediate_tasks() etc. — mock them to return empty
    with (
        patch("apps.tasks.cron_scheduler.close_old_connections"),
        patch("apps.tasks.models.Task.immediate_tasks", return_value=Task.objects.none()),
        patch("apps.tasks.models.Task.scheduled_tasks", return_value=Task.objects.none()),
        patch("apps.tasks.models.Task.recurring_tasks", return_value=Task.objects.none()),
        patch.object(scheduler, "_retry_failed_tasks"),
    ):
        scheduler._periodic_database_sync()

    task.refresh_from_db()
    execution.refresh_from_db()
    assert task.status == "failed"
    assert execution.status == "failed"


# ---------------------------------------------------------------------------
# _fail_stuck_tasks — TASK_TIMEOUT_TYPE="created" anchor
# ---------------------------------------------------------------------------
@pytest.mark.unit
@pytest.mark.django_db
def test_fail_stuck_tasks_created_type_overtime(user, mock_apscheduler):
    """Task with TASK_ABSOLUTE_TIMEOUT_SECONDS is failed when created timestamp is past deadline."""
    import apps.tasks.cron_scheduler as cs
    from apps.tasks.models import Task, TaskExecution

    task_timeout = 300
    task = Task.objects.create(
        name="created_stuck",
        function_name="hello_world",
        task_data={"TASK_ABSOLUTE_TIMEOUT_SECONDS": task_timeout},
        created_by=user,
        status="running",
    )
    # Backdate created so it's past deadline (timeout + padding + 1s)
    overtime = timezone.now() - timedelta(seconds=task_timeout + cs.STUCK_TASK_TIMEOUT_PADDING_SECONDS + 1)
    Task.objects.filter(pk=task.pk).update(created=overtime)
    execution = TaskExecution.objects.create(task=task, status="running")

    scheduler = cs.UnifiedTaskScheduler()
    scheduler._fail_stuck_tasks()

    task.refresh_from_db()
    execution.refresh_from_db()
    assert task.status == "failed"
    assert execution.status == "failed"


@pytest.mark.unit
@pytest.mark.django_db
def test_fail_stuck_tasks_created_type_within_deadline(user, mock_apscheduler):
    """Task with TASK_ABSOLUTE_TIMEOUT_SECONDS is NOT failed when still within its deadline."""
    import apps.tasks.cron_scheduler as cs
    from apps.tasks.models import Task, TaskExecution

    task = Task.objects.create(
        name="created_ok",
        function_name="hello_world",
        task_data={"TASK_ABSOLUTE_TIMEOUT_SECONDS": 420},
        created_by=user,
        status="running",
    )
    # created is very recent — well within deadline
    execution = TaskExecution.objects.create(task=task, status="running")

    scheduler = cs.UnifiedTaskScheduler()
    scheduler._fail_stuck_tasks()

    task.refresh_from_db()
    assert task.status == "running"
    execution.refresh_from_db()
    assert execution.status == "running"


@pytest.mark.unit
@pytest.mark.django_db
def test_fail_stuck_tasks_per_task_timeout_override(user, mock_apscheduler):
    """Per-task TASK_TIMEOUT_SECONDS overrides the global timeout for stuck detection."""
    import apps.tasks.cron_scheduler as cs
    from apps.tasks.models import Task, TaskExecution

    short_timeout = 60
    task = Task.objects.create(
        name="short_timeout_stuck",
        function_name="hello_world",
        task_data={"TASK_TIMEOUT_SECONDS": short_timeout},
        created_by=user,
        status="running",
    )
    # Backdate started_at past the short timeout + padding
    started = timezone.now() - timedelta(seconds=short_timeout + cs.STUCK_TASK_TIMEOUT_PADDING_SECONDS + 1)
    Task.objects.filter(pk=task.pk).update(started_at=started)
    execution = TaskExecution.objects.create(task=task, status="running")

    scheduler = cs.UnifiedTaskScheduler()
    scheduler._fail_stuck_tasks()

    task.refresh_from_db()
    execution.refresh_from_db()
    assert task.status == "failed"
    assert execution.status == "failed"


@pytest.mark.unit
@pytest.mark.django_db
def test_fail_stuck_tasks_skips_task_without_started_at(user, mock_apscheduler):
    """Running task with no started_at and no TASK_ABSOLUTE_TIMEOUT_SECONDS is not failed."""
    import apps.tasks.cron_scheduler as cs
    from apps.tasks.models import Task, TaskExecution

    task = Task.objects.create(
        name="no_started_at",
        function_name="hello_world",
        task_data={},
        created_by=user,
        status="running",
    )
    # Ensure started_at is None
    Task.objects.filter(pk=task.pk).update(started_at=None)
    execution = TaskExecution.objects.create(task=task, status="running")

    scheduler = cs.UnifiedTaskScheduler()
    scheduler._fail_stuck_tasks()

    task.refresh_from_db()
    assert task.status == "running"
    execution.refresh_from_db()
    assert execution.status == "running"


# ---------------------------------------------------------------------------
# get_scheduler singleton
# ---------------------------------------------------------------------------
@pytest.mark.unit
def test_get_scheduler_returns_same_instance():
    import apps.tasks.cron_scheduler as cs

    cs._scheduler_instance = None
    s1 = cs.get_scheduler()
    s2 = cs.get_scheduler()
    assert s1 is s2
    cs._scheduler_instance = None  # cleanup


# ---------------------------------------------------------------------------
# _fail_stuck_tasks — started_at ok but absolute timeout exceeded
# ---------------------------------------------------------------------------
@pytest.mark.unit
@pytest.mark.django_db
def test_fail_stuck_tasks_absolute_fires_when_started_at_within_relative(user, mock_apscheduler):
    """Task whose started_at is within the relative timeout but created exceeds absolute is failed."""
    import apps.tasks.cron_scheduler as cs
    from apps.tasks.models import Task, TaskExecution

    abs_timeout = 300
    task = Task.objects.create(
        name="abs_only_stuck",
        function_name="hello_world",
        task_data={"TASK_ABSOLUTE_TIMEOUT_SECONDS": abs_timeout},
        created_by=user,
        status="running",
    )
    # created is well past the absolute deadline
    overtime_created = timezone.now() - timedelta(seconds=abs_timeout + cs.STUCK_TASK_TIMEOUT_PADDING_SECONDS + 1)
    # started_at is very recent — within the relative timeout
    recent_started = timezone.now() - timedelta(seconds=10)
    Task.objects.filter(pk=task.pk).update(created=overtime_created, started_at=recent_started)
    execution = TaskExecution.objects.create(task=task, status="running")

    scheduler = cs.UnifiedTaskScheduler()
    scheduler._fail_stuck_tasks()

    task.refresh_from_db()
    execution.refresh_from_db()
    assert task.status == "failed"
    assert execution.status == "failed"
    assert "TASK_ABSOLUTE_TIMEOUT_SECONDS" in task.error_message


# ---------------------------------------------------------------------------
# _retry_failed_tasks
# ---------------------------------------------------------------------------
@pytest.mark.unit
@pytest.mark.django_db
def test_retry_failed_tasks_calls_schedule_retry(user, mock_apscheduler):
    """Failed task without absolute timeout has _schedule_retry called."""
    import apps.tasks.cron_scheduler as cs
    from apps.tasks.models import Task

    task = Task.objects.create(
        name="retry_me",
        function_name="hello_world",
        task_data={},
        created_by=user,
        status="failed",
        attempts=1,
        max_attempts=3,
    )

    scheduler = cs.UnifiedTaskScheduler()
    with patch("apps.tasks.tasks_system._schedule_retry") as mock_retry:
        scheduler._retry_failed_tasks()

    mock_retry.assert_called_once_with(task)


@pytest.mark.unit
@pytest.mark.django_db
def test_retry_failed_tasks_skips_when_absolute_timeout_elapsed(user, mock_apscheduler):
    """Failed task with elapsed absolute timeout is not retried; error_message is updated."""
    import apps.tasks.cron_scheduler as cs
    from apps.tasks.models import Task

    abs_timeout = 120
    task = Task.objects.create(
        name="abs_elapsed_retry",
        function_name="hello_world",
        task_data={"TASK_ABSOLUTE_TIMEOUT_SECONDS": abs_timeout},
        created_by=user,
        status="failed",
        attempts=1,
        max_attempts=5,
    )
    # created is past the absolute timeout
    old_created = timezone.now() - timedelta(seconds=abs_timeout + 1)
    Task.objects.filter(pk=task.pk).update(created=old_created)

    scheduler = cs.UnifiedTaskScheduler()
    with patch("apps.tasks.tasks_system._schedule_retry") as mock_retry:
        scheduler._retry_failed_tasks()

    mock_retry.assert_not_called()
    task.refresh_from_db()
    assert "no further retries" in task.error_message


@pytest.mark.unit
@pytest.mark.django_db
def test_retry_failed_tasks_exhausts_attempts_on_absolute_timeout(user, mock_apscheduler):
    """When absolute timeout elapses, attempts is set to max_attempts so the task
    drops out of the retryable queryset (attempts__lt=max_attempts) on the next tick."""
    import apps.tasks.cron_scheduler as cs
    from apps.tasks.models import Task

    abs_timeout = 120
    task = Task.objects.create(
        name="already_msg_task",
        function_name="hello_world",
        task_data={"TASK_ABSOLUTE_TIMEOUT_SECONDS": abs_timeout},
        created_by=user,
        status="failed",
        attempts=1,
        max_attempts=5,
    )
    old_created = timezone.now() - timedelta(seconds=abs_timeout + 1)
    Task.objects.filter(pk=task.pk).update(created=old_created)

    scheduler = cs.UnifiedTaskScheduler()
    scheduler._retry_failed_tasks()

    task.refresh_from_db()
    assert task.attempts == task.max_attempts
    assert "no further retries" in task.error_message
    # Confirm the task no longer appears in the retryable queryset
    from django.db.models import F

    assert not Task.objects.filter(pk=task.pk, attempts__lt=F("max_attempts")).exists()


@pytest.mark.unit
@pytest.mark.django_db
def test_retry_failed_tasks_retries_within_absolute_deadline(user, mock_apscheduler):
    """Failed task whose absolute timeout has NOT elapsed is retried normally."""
    import apps.tasks.cron_scheduler as cs
    from apps.tasks.models import Task

    task = Task.objects.create(
        name="within_deadline_retry",
        function_name="hello_world",
        task_data={"TASK_ABSOLUTE_TIMEOUT_SECONDS": 600},
        created_by=user,
        status="failed",
        attempts=1,
        max_attempts=5,
    )

    scheduler = cs.UnifiedTaskScheduler()
    with patch("apps.tasks.tasks_system._schedule_retry") as mock_retry:
        scheduler._retry_failed_tasks()

    mock_retry.assert_called_once_with(task)
