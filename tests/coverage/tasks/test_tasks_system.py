"""
Unit tests for apps/tasks/tasks_system.py.
Targets 14.9% → ~90% coverage.
"""

from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# _claim_task
# ---------------------------------------------------------------------------
@pytest.mark.unit
@pytest.mark.django_db
def test_claim_task_succeeds_for_pending(user):
    from apps.tasks.models import Task
    from apps.tasks.tasks_system import _claim_task

    task = Task.objects.create(name="pending_task", function_name="hello_world", task_data={}, created_by=user)
    task_obj, execution = _claim_task(task.id)

    assert task_obj is not None
    assert execution is not None
    task.refresh_from_db()
    assert task.status == "running"


@pytest.mark.unit
@pytest.mark.django_db
def test_claim_task_returns_none_for_running(user):
    from apps.tasks.models import Task
    from apps.tasks.tasks_system import _claim_task

    task = Task.objects.create(
        name="running_task", function_name="hello_world", task_data={}, created_by=user, status="running"
    )
    task_obj, execution = _claim_task(task.id)

    assert task_obj is None
    assert execution is None


@pytest.mark.unit
@pytest.mark.django_db
def test_claim_task_returns_none_for_completed(user):
    from apps.tasks.models import Task
    from apps.tasks.tasks_system import _claim_task

    task = Task.objects.create(
        name="done_task", function_name="hello_world", task_data={}, created_by=user, status="completed"
    )
    task_obj, execution = _claim_task(task.id)
    assert task_obj is None


# ---------------------------------------------------------------------------
# execute_db_task
# ---------------------------------------------------------------------------
@pytest.mark.unit
def test_execute_db_task_no_task_id():
    from apps.tasks.tasks_system import execute_db_task

    result = execute_db_task()
    assert result["status"] == "error"
    assert "task_id" in result["error"]


@pytest.mark.unit
@pytest.mark.django_db
def test_execute_db_task_nonexistent_id():
    from apps.tasks.tasks_system import execute_db_task

    result = execute_db_task(task_id=999999)
    assert result["status"] == "error"


@pytest.mark.unit
@pytest.mark.django_db
def test_execute_db_task_success(user, mock_dispatcherd, mock_dispatcherd_config):
    from apps.tasks.models import Task
    from apps.tasks.tasks_system import execute_db_task

    task = Task.objects.create(name="exec_task", function_name="hello_world", task_data={}, created_by=user)

    mock_fn = MagicMock(return_value={"status": "success", "message": "ok"})
    with patch.dict("apps.tasks.tasks.TASK_FUNCTIONS", {"hello_world": mock_fn}):
        result = execute_db_task(task_id=task.id)

    assert result["status"] == "success"
    task.refresh_from_db()
    assert task.status == "completed"


@pytest.mark.unit
@pytest.mark.django_db
def test_execute_db_task_function_not_in_registry(user):
    from apps.tasks.models import Task
    from apps.tasks.tasks_system import execute_db_task

    task = Task.objects.create(
        name="missing_fn_task", function_name="nonexistent_function", task_data={}, created_by=user
    )

    with patch.dict("apps.tasks.tasks.TASK_FUNCTIONS", {}, clear=True):
        result = execute_db_task(task_id=task.id)

    assert result["status"] == "error"
    task.refresh_from_db()
    assert task.status == "failed"


@pytest.mark.unit
@pytest.mark.django_db
def test_execute_db_task_function_returns_error(user):
    """When a task function returns error status, execute_db_task propagates the error."""
    from apps.tasks.models import Task
    from apps.tasks.tasks_system import execute_db_task

    task = Task.objects.create(name="raise_task_3", function_name="hello_world", task_data={}, created_by=user)

    mock_fn = MagicMock(return_value={"status": "error", "error": "task error occurred"})
    with (
        patch.dict("apps.tasks.tasks.TASK_FUNCTIONS", {"hello_world": mock_fn}),
        patch("apps.tasks.tasks.TASK_LOCKS", set()),
    ):
        result = execute_db_task(task_id=task.id)

    # The task function was called and returned an error
    assert result["status"] == "error"
    mock_fn.assert_called_once()


@pytest.mark.unit
@pytest.mark.django_db
def test_execute_db_task_fails_when_already_claimed(user):
    """If the task is already claimed by another worker, returns error."""
    from apps.tasks.models import Task
    from apps.tasks.tasks_system import execute_db_task

    task = Task.objects.create(
        name="already_claimed", function_name="hello_world", task_data={}, created_by=user, status="running"
    )
    result = execute_db_task(task_id=task.id)
    assert result["status"] == "error"


# ---------------------------------------------------------------------------
# execute_claimed — auto-retry on failure
# ---------------------------------------------------------------------------
@pytest.mark.unit
@pytest.mark.django_db
def test_execute_claimed_task_failure_returns_error(user):
    """When a task function returns error, execute_claimed propagates error status."""
    from apps.tasks.models import Task, TaskExecution
    from apps.tasks.tasks_system import execute_claimed

    task = Task.objects.create(
        name="t_fail2", function_name="hello_world", task_data={}, created_by=user, status="running", attempts=1
    )
    execution = TaskExecution.objects.create(task=task, status="running", worker_id="test-1")

    mock_fn = MagicMock(return_value={"status": "error", "error": "failed"})
    with (
        patch.dict("apps.tasks.tasks.TASK_FUNCTIONS", {"hello_world": mock_fn}),
        patch("apps.tasks.tasks.TASK_LOCKS", set()),
    ):
        result = execute_claimed(task, execution)

    assert result["status"] == "error"
    mock_fn.assert_called_once()


# ---------------------------------------------------------------------------
# submit_task_to_dispatcher
# ---------------------------------------------------------------------------
@pytest.mark.unit
@pytest.mark.django_db
def test_submit_task_to_dispatcher_calls_submit(user, mock_dispatcherd, mock_dispatcherd_config):
    from apps.tasks.models import Task
    from apps.tasks.tasks_system import submit_task_to_dispatcher

    task = Task.objects.create(name="dispatch_task", function_name="hello_world", task_data={}, created_by=user)

    submit_task_to_dispatcher(task)
    mock_dispatcherd.assert_called_once()


@pytest.mark.unit
@pytest.mark.django_db
def test_submit_task_skips_if_pending_execution_exists(user, mock_dispatcherd, mock_dispatcherd_config):
    from apps.tasks.models import Task, TaskExecution
    from apps.tasks.tasks_system import submit_task_to_dispatcher

    task = Task.objects.create(name="skip_task", function_name="hello_world", task_data={}, created_by=user)
    TaskExecution.objects.create(task=task, status="pending")

    submit_task_to_dispatcher(task)
    mock_dispatcherd.assert_not_called()


@pytest.mark.unit
@pytest.mark.django_db
def test_submit_task_handles_submit_error(user, mock_dispatcherd_config):
    from apps.tasks.models import Task
    from apps.tasks.tasks_system import submit_task_to_dispatcher

    task = Task.objects.create(name="err_task", function_name="hello_world", task_data={}, created_by=user)

    with patch("dispatcherd.publish.submit_task", side_effect=RuntimeError("broker down")):
        submit_task_to_dispatcher(task)

    task.refresh_from_db()
    assert task.status == "failed"
    assert "broker down" in task.error_message


@pytest.mark.unit
@pytest.mark.django_db
def test_submit_task_dispatcher_error_logs_warning_when_retriable(user, mock_dispatcherd_config):
    """submit_task_to_dispatcher logs WARNING when task still has retry attempts remaining."""
    from apps.tasks.models import Task
    from apps.tasks.tasks_system import submit_task_to_dispatcher

    # attempts=0, max_attempts=3 → can_retry() returns True after status set to "failed"
    task = Task.objects.create(
        name="retry_dispatch_task",
        function_name="hello_world",
        task_data={},
        created_by=user,
        attempts=0,
        max_attempts=3,
    )

    with (
        patch("dispatcherd.publish.submit_task", side_effect=RuntimeError("broker unavailable")),
        patch("apps.tasks.tasks_system.logger") as mock_logger,
    ):
        submit_task_to_dispatcher(task)

    task.refresh_from_db()
    assert task.status == "failed"
    mock_logger.warning.assert_called_once()
    warning_msg = mock_logger.warning.call_args[0][0]
    assert "broker unavailable" in warning_msg
    # Must NOT log at ERROR level for the dispatcher error
    error_calls = [str(call) for call in mock_logger.error.call_args_list]
    assert not any("broker unavailable" in c for c in error_calls)


@pytest.mark.unit
@pytest.mark.django_db
def test_submit_task_dispatcher_error_logs_error_when_exhausted(user, mock_dispatcherd_config):
    """submit_task_to_dispatcher logs ERROR when task has no retry attempts remaining."""
    from apps.tasks.models import Task
    from apps.tasks.tasks_system import submit_task_to_dispatcher

    # attempts == max_attempts → can_retry() returns False
    task = Task.objects.create(
        name="exhausted_dispatch_task",
        function_name="hello_world",
        task_data={},
        created_by=user,
        attempts=3,
        max_attempts=3,
    )

    with (
        patch("dispatcherd.publish.submit_task", side_effect=RuntimeError("broker gone")),
        patch("apps.tasks.tasks_system.logger") as mock_logger,
    ):
        submit_task_to_dispatcher(task)

    task.refresh_from_db()
    assert task.status == "failed"
    mock_logger.error.assert_called_once()
    error_msg = mock_logger.error.call_args[0][0]
    assert "broker gone" in error_msg
    # Must NOT log at WARNING level for the dispatcher error
    warning_calls = [str(call) for call in mock_logger.warning.call_args_list]
    assert not any("broker gone" in c for c in warning_calls)


# ---------------------------------------------------------------------------
# submit_task_to_dispatcher — timeout handling
# ---------------------------------------------------------------------------
@pytest.mark.unit
@pytest.mark.django_db
def test_submit_task_passes_explicit_timeout(user, mock_dispatcherd, mock_dispatcherd_config):
    """TASK_TIMEOUT_SECONDS in task_data is forwarded to dispatcherd as timeout."""
    from apps.tasks.models import Task
    from apps.tasks.tasks_system import submit_task_to_dispatcher

    task = Task.objects.create(
        name="timeout_task",
        function_name="hello_world",
        task_data={"TASK_TIMEOUT_SECONDS": 300},
        created_by=user,
    )

    submit_task_to_dispatcher(task)

    _, kwargs = mock_dispatcherd.call_args
    assert kwargs.get("timeout") == 300


@pytest.mark.unit
@pytest.mark.django_db
def test_submit_task_no_timeout_when_not_set(user, mock_dispatcherd, mock_dispatcherd_config):
    """task_data without TASK_TIMEOUT_SECONDS passes timeout=None to dispatcherd."""
    from apps.tasks.models import Task
    from apps.tasks.tasks_system import submit_task_to_dispatcher

    task = Task.objects.create(
        name="no_timeout_task",
        function_name="hello_world",
        task_data={},
        created_by=user,
    )

    submit_task_to_dispatcher(task)

    _, kwargs = mock_dispatcherd.call_args
    assert kwargs.get("timeout") is None


@pytest.mark.unit
@pytest.mark.django_db
def test_submit_task_shrinks_timeout_for_absolute_deadline(user, mock_dispatcherd, mock_dispatcherd_config):
    """TASK_ABSOLUTE_TIMEOUT_SECONDS shrinks the timeout by elapsed time since task creation."""
    from unittest.mock import patch

    from django.utils import timezone

    from apps.tasks.models import Task
    from apps.tasks.tasks_system import submit_task_to_dispatcher

    task = Task.objects.create(
        name="absolute_deadline_task",
        function_name="hello_world",
        task_data={"TASK_ABSOLUTE_TIMEOUT_SECONDS": 420},
        created_by=user,
    )
    # Simulate 60 seconds elapsed since creation
    fake_now = task.created + __import__("datetime").timedelta(seconds=60)
    with patch("django.utils.timezone.now", return_value=fake_now):
        submit_task_to_dispatcher(task)

    _, kwargs = mock_dispatcherd.call_args
    assert kwargs.get("timeout") == 360  # 420 - 60


@pytest.mark.unit
@pytest.mark.django_db
def test_submit_task_fails_immediately_when_absolute_deadline_elapsed(user, mock_dispatcherd, mock_dispatcherd_config):
    """Task is immediately failed without dispatch when TASK_ABSOLUTE_TIMEOUT_SECONDS has elapsed."""
    from unittest.mock import patch

    from apps.tasks.models import Task
    from apps.tasks.tasks_system import submit_task_to_dispatcher

    task = Task.objects.create(
        name="expired_task",
        function_name="hello_world",
        task_data={"TASK_ABSOLUTE_TIMEOUT_SECONDS": 60},
        created_by=user,
    )
    # Simulate 120 seconds elapsed — well past the absolute deadline
    fake_now = task.created + __import__("datetime").timedelta(seconds=120)
    with patch("django.utils.timezone.now", return_value=fake_now):
        submit_task_to_dispatcher(task)

    # Dispatcherd must NOT have been called — task was failed before submission
    mock_dispatcherd.assert_not_called()
    task.refresh_from_db()
    assert task.status == "failed"
    assert "absolute timeout" in task.error_message.lower()


# ---------------------------------------------------------------------------
# create_system_tasks
# ---------------------------------------------------------------------------
@pytest.mark.unit
@pytest.mark.django_db
def test_create_system_tasks_creates_all_enabled():
    from apps.tasks.models import Task
    from apps.tasks.tasks_system import create_system_tasks

    Task.objects.filter(is_system_task=True).delete()
    results = create_system_tasks()

    assert results["created"] > 0
    assert results.get("error") is None
    # Verify at least the system tasks exist in DB
    assert Task.objects.filter(is_system_task=True, function_name="cleanup_old_tasks").exists()
    assert Task.objects.filter(is_system_task=True, function_name="hello_world").exists()


@pytest.mark.unit
@pytest.mark.django_db
def test_create_system_tasks_removes_existing_before_recreate():
    from apps.tasks.models import Task
    from apps.tasks.tasks_system import create_system_tasks

    # Seed some system tasks first
    create_system_tasks()
    count_before = Task.objects.filter(is_system_task=True).count()

    results = create_system_tasks()
    assert results["removed"] == count_before


@pytest.mark.unit
@pytest.mark.django_db
def test_create_task_from_group_with_feature_flag():
    from apps.tasks.models import Task
    from apps.tasks.tasks_system import _create_task_from_group

    results = {"created": 0, "removed": 0, "tasks": []}
    config = {
        "function": "hello_world",
        "cron": "0 * * * *",
        "feature_flag": "METRICS_COLLECTION",
        "args": {"some_arg": 1},
        "description": "test task",
    }
    _create_task_from_group("test_flagged_task", config, results, Task)

    assert results["created"] == 1
    task = Task.objects.get(name="test_flagged_task")
    assert task.task_data.get("_feature_flag") == "METRICS_COLLECTION"
    assert task.task_data.get("some_arg") == 1


@pytest.mark.unit
@pytest.mark.django_db
def test_create_task_from_group_without_feature_flag():
    from apps.tasks.models import Task
    from apps.tasks.tasks_system import _create_task_from_group

    results = {"created": 0, "removed": 0, "tasks": []}
    config = {"function": "hello_world", "cron": None, "args": {}, "description": "no flag task"}
    _create_task_from_group("test_no_flag_task", config, results, Task)

    task = Task.objects.get(name="test_no_flag_task")
    assert "_feature_flag" not in task.task_data


# ---------------------------------------------------------------------------
# _get_exponent — invalid values fall back to default
# ---------------------------------------------------------------------------
@pytest.mark.unit
def test_get_exponent_value_le_one_falls_back():
    """retry_exponent <= 1 raises ValueError internally and falls back to RETRY_EXPONENT."""
    from unittest.mock import MagicMock

    from apps.tasks.tasks_system import RETRY_EXPONENT, _get_exponent

    task = MagicMock()
    task.task_data = {"retry_exponent": 0.5}
    task.name = "test_task"

    result = _get_exponent(task)
    assert result == RETRY_EXPONENT


@pytest.mark.unit
def test_get_exponent_non_numeric_falls_back():
    """Non-numeric retry_exponent falls back to RETRY_EXPONENT."""
    from unittest.mock import MagicMock

    from apps.tasks.tasks_system import RETRY_EXPONENT, _get_exponent

    task = MagicMock()
    task.task_data = {"retry_exponent": "not_a_number"}
    task.name = "test_task"

    result = _get_exponent(task)
    assert result == RETRY_EXPONENT


# ---------------------------------------------------------------------------
# _schedule_retry — early returns
# ---------------------------------------------------------------------------
@pytest.mark.unit
def test_schedule_retry_skips_when_cannot_retry_before_refresh():
    """_schedule_retry returns immediately if can_retry() is False on first check."""
    from unittest.mock import MagicMock

    from apps.tasks.tasks_system import _schedule_retry

    task = MagicMock()
    task.can_retry.return_value = False

    _schedule_retry(task)

    task.refresh_from_db.assert_not_called()
    task.retry.assert_not_called()


@pytest.mark.unit
def test_schedule_retry_skips_when_cannot_retry_after_refresh():
    """_schedule_retry returns after refresh if can_retry() becomes False."""
    from unittest.mock import MagicMock

    from apps.tasks.tasks_system import _schedule_retry

    task = MagicMock()
    task.can_retry.side_effect = [True, False]

    _schedule_retry(task)

    task.refresh_from_db.assert_called_once()
    task.retry.assert_not_called()


# ---------------------------------------------------------------------------
# execute_function — DispatcherCancel handling
# ---------------------------------------------------------------------------
@pytest.mark.unit
@pytest.mark.django_db
def test_execute_function_dispatcher_cancel_returns_error(user):
    """execute_function returns a cancel error when DispatcherCancel is raised."""
    from apps.tasks.models import Task, TaskExecution
    from apps.tasks.tasks_system import execute_function

    task = Task.objects.create(name="cancel_task", function_name="hello_world", task_data={}, created_by=user)
    execution = TaskExecution.objects.create(task=task, status="running")

    from dispatcherd.worker.exceptions import DispatcherCancel

    mock_fn = MagicMock(side_effect=DispatcherCancel())

    result = execute_function(task, execution, mock_fn, locked=False)

    assert result["status"] == "error"
    assert "cancelled by dispatcherd" in result["error"].lower()


@pytest.mark.unit
@pytest.mark.django_db
def test_execute_function_dispatcher_cancel_import_error_falls_through(user):
    """If DispatcherCancel cannot be imported, execute_function falls through to generic error."""
    import sys
    from unittest.mock import MagicMock

    from apps.tasks.models import Task, TaskExecution
    from apps.tasks.tasks_system import execute_function

    task = Task.objects.create(name="cancel_task2", function_name="hello_world", task_data={}, created_by=user)
    execution = TaskExecution.objects.create(task=task, status="running")

    mock_fn = MagicMock(side_effect=RuntimeError("boom"))

    with patch.dict(sys.modules, {"dispatcherd.worker.exceptions": None}):
        result = execute_function(task, execution, mock_fn, locked=False)

    assert result["status"] == "error"
    assert "boom" in result["error"]


# ---------------------------------------------------------------------------
# execute_db_task — outer exception handling
# ---------------------------------------------------------------------------
@pytest.mark.unit
@pytest.mark.django_db
def test_execute_db_task_outer_exception_is_handled(user):
    """Unexpected exception during _claim_task is caught and returns error."""
    from apps.tasks.models import Task
    from apps.tasks.tasks_system import execute_db_task

    task = Task.objects.create(name="outer_exc_task", function_name="hello_world", task_data={}, created_by=user)

    with patch("apps.tasks.tasks_system._claim_task", side_effect=RuntimeError("unexpected DB error")):
        result = execute_db_task(task_id=task.id)

    assert result["status"] == "error"


# ---------------------------------------------------------------------------
# submit_task_to_dispatcher — both TASK_TIMEOUT_SECONDS and TASK_ABSOLUTE_TIMEOUT_SECONDS
# ---------------------------------------------------------------------------
@pytest.mark.unit
@pytest.mark.django_db
def test_submit_task_takes_min_of_relative_and_remaining(user, mock_dispatcherd, mock_dispatcherd_config):
    """When both timeouts are set, dispatcherd receives min(relative, remaining)."""
    import datetime

    from django.utils import timezone

    from apps.tasks.models import Task
    from apps.tasks.tasks_system import submit_task_to_dispatcher

    task = Task.objects.create(
        name="both_timeout_task",
        function_name="hello_world",
        task_data={"TASK_TIMEOUT_SECONDS": 200, "TASK_ABSOLUTE_TIMEOUT_SECONDS": 420},
        created_by=user,
    )
    # 60s elapsed → remaining = 360s; min(200, 360) = 200
    fake_now = task.created + datetime.timedelta(seconds=60)
    with patch("django.utils.timezone.now", return_value=fake_now):
        submit_task_to_dispatcher(task)

    _, kwargs = mock_dispatcherd.call_args
    assert kwargs.get("timeout") == 200


@pytest.mark.unit
@pytest.mark.django_db
def test_submit_task_remaining_wins_when_tighter(user, mock_dispatcherd, mock_dispatcherd_config):
    """When remaining time < relative timeout, remaining governs."""
    import datetime

    from apps.tasks.models import Task
    from apps.tasks.tasks_system import submit_task_to_dispatcher

    task = Task.objects.create(
        name="remaining_wins_task",
        function_name="hello_world",
        task_data={"TASK_TIMEOUT_SECONDS": 400, "TASK_ABSOLUTE_TIMEOUT_SECONDS": 420},
        created_by=user,
    )
    # 60s elapsed → remaining = 360s; min(400, 360) = 360
    fake_now = task.created + datetime.timedelta(seconds=60)
    with patch("django.utils.timezone.now", return_value=fake_now):
        submit_task_to_dispatcher(task)

    _, kwargs = mock_dispatcherd.call_args
    assert kwargs.get("timeout") == 360


# ---------------------------------------------------------------------------
# _safe_timeout_int — unit tests
# ---------------------------------------------------------------------------
@pytest.mark.unit
def test_safe_timeout_int_valid_positive_value():
    """A valid positive integer is returned unchanged."""
    from apps.tasks.tasks_system import _safe_timeout_int

    assert _safe_timeout_int(300, field="TASK_TIMEOUT_SECONDS", task_id=1) == 300


@pytest.mark.unit
def test_safe_timeout_int_string_numeric_coerced():
    """A string that represents a positive integer is accepted."""
    from apps.tasks.tasks_system import _safe_timeout_int

    assert _safe_timeout_int("600", field="TASK_TIMEOUT_SECONDS", task_id=1) == 600


@pytest.mark.unit
def test_safe_timeout_int_non_numeric_returns_default():
    """A non-numeric string returns the supplied default and does not raise."""
    from apps.tasks.tasks_system import _safe_timeout_int

    assert _safe_timeout_int("bad_value", field="TASK_TIMEOUT_SECONDS", task_id=1, default=None) is None


@pytest.mark.unit
def test_safe_timeout_int_zero_returns_default():
    """Zero is non-positive and must be rejected (returns default)."""
    from apps.tasks.tasks_system import _safe_timeout_int

    assert _safe_timeout_int(0, field="TASK_TIMEOUT_SECONDS", task_id=1, default=None) is None


@pytest.mark.unit
def test_safe_timeout_int_negative_returns_default():
    """A negative value is non-positive and must be rejected (returns default)."""
    from apps.tasks.tasks_system import _safe_timeout_int

    assert _safe_timeout_int(-60, field="TASK_TIMEOUT_SECONDS", task_id=1, default=None) is None


@pytest.mark.unit
def test_safe_timeout_int_none_input_returns_default_silently():
    """None input returns the supplied default without logging a warning."""
    from apps.tasks.tasks_system import _safe_timeout_int

    with patch("apps.tasks.tasks_system.logger") as mock_logger:
        result = _safe_timeout_int(None, field="TASK_TIMEOUT_SECONDS", task_id=1, default=99)

    assert result == 99
    mock_logger.warning.assert_not_called()


@pytest.mark.unit
def test_safe_timeout_int_invalid_value_logs_warning():
    """An invalid value must emit exactly one logger.warning."""
    from apps.tasks.tasks_system import _safe_timeout_int

    with patch("apps.tasks.tasks_system.logger") as mock_logger:
        _safe_timeout_int("oops", field="TASK_TIMEOUT_SECONDS", task_id=42, default=None)

    mock_logger.warning.assert_called_once()
    assert "TASK_TIMEOUT_SECONDS" in mock_logger.warning.call_args[0][0]
    assert "oops" in mock_logger.warning.call_args[0][0]


# ---------------------------------------------------------------------------
# submit_task_to_dispatcher — malformed / non-positive timeout values
# ---------------------------------------------------------------------------
@pytest.mark.unit
@pytest.mark.django_db
def test_submit_task_malformed_absolute_timeout_still_submits(user, mock_dispatcherd, mock_dispatcherd_config):
    """Malformed TASK_ABSOLUTE_TIMEOUT_SECONDS is silently dropped; the task is still submitted.

    Before the fix, int("bad") raised ValueError into the except block, which did not
    increment attempts, creating an infinite retry loop.  After the fix _safe_timeout_int
    returns None and the submit proceeds normally.
    """
    from apps.tasks.models import Task
    from apps.tasks.tasks_system import submit_task_to_dispatcher

    task = Task.objects.create(
        name="bad_abs_timeout_task",
        function_name="hello_world",
        task_data={"TASK_ABSOLUTE_TIMEOUT_SECONDS": "not_a_number"},
        created_by=user,
    )
    submit_task_to_dispatcher(task)

    mock_dispatcherd.assert_called_once()
    _, kwargs = mock_dispatcherd.call_args
    # Malformed value is dropped → timeout falls back to None (dispatcherd default)
    assert kwargs.get("timeout") is None
    task.refresh_from_db()
    assert task.status == "pending"
    # No error path taken — attempts must NOT have been incremented
    assert task.attempts == 0


@pytest.mark.unit
@pytest.mark.django_db
def test_submit_task_malformed_relative_timeout_still_submits(user, mock_dispatcherd, mock_dispatcherd_config):
    """Malformed TASK_TIMEOUT_SECONDS is dropped; task is submitted with timeout=None."""
    from apps.tasks.models import Task
    from apps.tasks.tasks_system import submit_task_to_dispatcher

    task = Task.objects.create(
        name="bad_rel_timeout_task",
        function_name="hello_world",
        task_data={"TASK_TIMEOUT_SECONDS": "oops"},
        created_by=user,
    )
    submit_task_to_dispatcher(task)

    mock_dispatcherd.assert_called_once()
    _, kwargs = mock_dispatcherd.call_args
    assert kwargs.get("timeout") is None
    task.refresh_from_db()
    assert task.status == "pending"
    assert task.attempts == 0


@pytest.mark.unit
@pytest.mark.django_db
def test_submit_task_zero_absolute_timeout_treated_as_absent(user, mock_dispatcherd, mock_dispatcherd_config):
    """TASK_ABSOLUTE_TIMEOUT_SECONDS=0 is non-positive; treated as absent so no early-fail occurs."""
    from apps.tasks.models import Task
    from apps.tasks.tasks_system import submit_task_to_dispatcher

    task = Task.objects.create(
        name="zero_abs_timeout_task",
        function_name="hello_world",
        task_data={"TASK_ABSOLUTE_TIMEOUT_SECONDS": 0},
        created_by=user,
    )
    submit_task_to_dispatcher(task)

    mock_dispatcherd.assert_called_once()
    task.refresh_from_db()
    assert task.status == "pending"


@pytest.mark.unit
@pytest.mark.django_db
def test_submit_task_negative_absolute_timeout_treated_as_absent(user, mock_dispatcherd, mock_dispatcherd_config):
    """TASK_ABSOLUTE_TIMEOUT_SECONDS=-1 is non-positive; treated as absent so no early-fail occurs."""
    from apps.tasks.models import Task
    from apps.tasks.tasks_system import submit_task_to_dispatcher

    task = Task.objects.create(
        name="neg_abs_timeout_task",
        function_name="hello_world",
        task_data={"TASK_ABSOLUTE_TIMEOUT_SECONDS": -1},
        created_by=user,
    )
    submit_task_to_dispatcher(task)

    mock_dispatcherd.assert_called_once()
    task.refresh_from_db()
    assert task.status == "pending"


# ---------------------------------------------------------------------------
# submit_task_to_dispatcher — attempts incremented on submit error
# ---------------------------------------------------------------------------
@pytest.mark.unit
@pytest.mark.django_db
def test_submit_task_error_increments_attempts(user, mock_dispatcherd_config):
    """A submit-time error increments attempts so _retry_failed_tasks can exhaust max_attempts.

    Without the fix the except block saved status='failed' without touching attempts,
    leaving the task permanently retryable and creating an infinite scheduler loop.
    """
    from apps.tasks.models import Task
    from apps.tasks.tasks_system import submit_task_to_dispatcher

    task = Task.objects.create(
        name="attempt_inc_task",
        function_name="hello_world",
        task_data={},
        created_by=user,
        attempts=0,
        max_attempts=3,
    )

    with patch("dispatcherd.publish.submit_task", side_effect=RuntimeError("broker down")):
        submit_task_to_dispatcher(task)

    task.refresh_from_db()
    assert task.status == "failed"
    assert task.attempts == 1


@pytest.mark.unit
@pytest.mark.django_db
def test_submit_task_repeated_errors_exhaust_max_attempts(user, mock_dispatcherd_config):
    """Repeated submit-time failures eventually exhaust max_attempts, stopping the retry loop."""
    from apps.tasks.models import Task
    from apps.tasks.tasks_system import _schedule_retry, submit_task_to_dispatcher

    task = Task.objects.create(
        name="exhaust_submit_task",
        function_name="hello_world",
        task_data={},
        created_by=user,
        attempts=0,
        max_attempts=2,
    )

    # Two submit failures should consume all attempts
    for _ in range(2):
        task.status = "pending"
        task.save(update_fields=["status", "modified"])
        with patch("dispatcherd.publish.submit_task", side_effect=RuntimeError("broker down")):
            submit_task_to_dispatcher(task)
        task.refresh_from_db()
        assert task.status == "failed"

    assert task.attempts == 2
    # Now max_attempts is reached; _schedule_retry must not reschedule
    _schedule_retry(task)
    task.refresh_from_db()
    assert task.status == "failed", "Task must not be rescheduled after max_attempts is exhausted"
