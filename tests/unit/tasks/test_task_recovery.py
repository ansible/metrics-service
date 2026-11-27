"""Recovery and finalization interleavings against real PostgreSQL connections."""

import logging
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from queue import Queue
from threading import Event
from time import monotonic
from unittest.mock import patch

import pytest
from django.conf import settings
from django.db import close_old_connections, connection, connections, transaction
from django.utils import timezone

from apps.analytics.v1.views import _fail_stale
from apps.tasks.cron_scheduler import UnifiedTaskScheduler
from apps.tasks.models import Task, TaskExecution
from apps.tasks.tasks_system import _claim_task, execute_db_task
from apps.tasks.utils import fail_stuck_tasks, handle_task_error, update_task_status

pytestmark = [pytest.mark.unit, pytest.mark.django_db(transaction=True)]


@pytest.fixture(autouse=True)
def bounded_database_waits() -> Iterator[None]:
    """Make a broken locking protocol fail rather than hang the test process."""
    with connection.cursor() as cursor:
        cursor.execute("SET lock_timeout = '5s'")
        cursor.execute("SET statement_timeout = '10s'")
    try:
        yield
    finally:
        with connection.cursor() as cursor:
            cursor.execute("RESET lock_timeout")
            cursor.execute("RESET statement_timeout")


def _claimed_task() -> tuple[Task, TaskExecution]:
    task = Task.objects.create(name="Recovery interleaving", function_name="hello_world")
    return _claim_task(task.pk)


def _age_claim(task: Task, execution: TaskExecution) -> None:
    old = timezone.now() - timedelta(seconds=settings.TASK_TIMEOUT + 10)
    Task.objects.filter(pk=task.pk).update(started_at=old)
    TaskExecution.objects.filter(pk=execution.pk).update(started_at=old)


def _on_connection[T](operation: Callable[[], T], backend: Queue[int]) -> T:
    """Run an operation on an independent, bounded PostgreSQL connection."""
    close_old_connections()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SET lock_timeout = '5s'")
            cursor.execute("SET statement_timeout = '10s'")
            cursor.execute("SELECT pg_backend_pid()")
            backend.put(cursor.fetchone()[0])
        return operation()
    finally:
        connections.close_all()


def _wait_for_database_lock(backend_pid: int) -> None:
    """Wait for PostgreSQL to confirm the contender is blocked, not just started."""
    deadline = monotonic() + 5
    pause = Event()
    while monotonic() < deadline:
        with connection.cursor() as cursor:
            cursor.execute("SELECT cardinality(pg_blocking_pids(%s))", [backend_pid])
            if cursor.fetchone()[0]:
                return
        pause.wait(0.01)
    pytest.fail("The competing connection never reached the held database lock")


def test_cancelled_dead_worker_execution_is_recovered_without_retry() -> None:
    """Cancellation is terminal for the Task, not an excuse to strand its attempt."""
    task, execution = _claimed_task()
    _age_claim(task, execution)
    assert task.cancel()
    completed_at = task.completed_at
    # Recovery must use the attempt's clock, not the parent's lifecycle fields.
    Task.objects.filter(pk=task.pk).update(started_at=None)

    scheduler = UnifiedTaskScheduler()
    scheduler._fail_stuck_tasks()
    scheduler._retry_failed_tasks()

    task.refresh_from_db()
    execution.refresh_from_db()
    assert task.status == "cancelled"
    assert task.completed_at == completed_at
    assert task.attempts == 1
    assert execution.status == "failed"
    assert execution.completed_at is not None
    assert execution.execution_time_seconds >= settings.TASK_TIMEOUT
    assert "timed out" in execution.error_message
    assert task.executions.count() == 1


@pytest.mark.parametrize("execution_status", ["running", "completed", "failed"])
def test_cancelled_recovery_preserves_fresh_or_terminal_executions(execution_status: str) -> None:
    """An old parent timestamp does not make a fresh/finished attempt recoverable."""
    task, execution = _claimed_task()
    _age_claim(task, execution)
    assert task.cancel()
    updates = {"status": execution_status}
    if execution_status == "running":
        updates["started_at"] = timezone.now()
    else:
        updates["completed_at"] = timezone.now() - timedelta(seconds=1)
    TaskExecution.objects.filter(pk=execution.pk).update(**updates)

    UnifiedTaskScheduler()._fail_stuck_tasks()

    execution.refresh_from_db()
    assert execution.status == execution_status
    assert execution.completed_at == updates.get("completed_at")


def test_cancelled_pending_task_does_not_gain_an_execution() -> None:
    """Cancelling unclaimed work does not manufacture an attempt during recovery."""
    task = Task.objects.create(name="Unclaimed cancellation", function_name="hello_world")
    assert task.cancel()

    UnifiedTaskScheduler()._fail_stuck_tasks()

    task.refresh_from_db()
    assert task.status == "cancelled"
    assert task.attempts == 0
    assert not task.executions.exists()


def test_analytics_stale_recovery_preserves_caller_driven_retry_policy() -> None:
    """A real exhausted analytics claim is requeued without resetting its budget."""
    task = Task.objects.create(
        name="On-demand recovery",
        function_name="collect_analytics_on_demand",
        task_data={"collector": "controller.unified_jobs_dashboard"},
        max_attempts=1,
    )
    task, execution = _claim_task(task.pk)
    _age_claim(task, execution)

    assert _fail_stale(task, timezone.now()) is True

    task.refresh_from_db()
    execution.refresh_from_db()
    assert task.status == "pending"
    assert task.attempts == task.max_attempts == 1
    assert execution.status == "failed"
    assert task.executions.count() == 1
    task, next_execution = _claim_task(task.pk)
    assert task.attempts == 2
    assert next_execution.pk != execution.pk


@pytest.mark.parametrize("finalizer", ["completed", "failed", "exception"])
def test_late_result_after_cancelled_execution_timeout_is_ignored(finalizer: str) -> None:
    """The timeout closes history even if a purportedly dead worker later returns."""
    task, execution = _claimed_task()
    _age_claim(task, execution)
    assert task.cancel()
    UnifiedTaskScheduler()._fail_stuck_tasks()
    execution.refresh_from_db()
    timeout_error = execution.error_message
    completed_at = execution.completed_at

    if finalizer == "exception":
        handle_task_error(task, execution, "late exception")
    else:
        update_task_status(task, execution, finalizer, result_data={"late": True}, error_message="late result")

    task.refresh_from_db()
    execution.refresh_from_db()
    assert task.status == "cancelled"
    assert execution.status == "failed"
    assert execution.error_message == timeout_error
    assert execution.completed_at == completed_at
    assert execution.result_data == {}


@pytest.mark.parametrize("recovery", ["scheduler", "analytics"])
def test_recovery_waiting_for_task_does_not_lock_execution_first(recovery: str) -> None:
    """A finalizer holding Task must not deadlock against a recovery holding its attempt."""
    task, execution = _claimed_task()
    _age_claim(task, execution)
    backend: Queue[int] = Queue()

    def recover() -> None:
        if recovery == "analytics":
            _fail_stale(Task.objects.get(pk=task.pk), timezone.now())
        else:
            UnifiedTaskScheduler()._fail_stuck_tasks()

    with ThreadPoolExecutor(max_workers=1) as executor:
        with transaction.atomic():
            Task.objects.select_for_update().get(pk=task.pk)
            future = executor.submit(_on_connection, recover, backend)
            _wait_for_database_lock(backend.get(timeout=5))
            update_task_status(task, execution, "completed", result_data={"winner": "worker"})
        future.result(timeout=10)

    task.refresh_from_db()
    execution.refresh_from_db()
    assert task.status == "completed"
    assert execution.status == "completed"
    assert execution.result_data == {"winner": "worker"}


@pytest.mark.parametrize("finalizer", ["completed", "failed", "exception"])
def test_waiting_old_worker_cannot_finalize_a_new_claim(finalizer: str) -> None:
    """A claim predicate evaluated before a lock wait must be rechecked afterwards."""
    task, execution = _claimed_task()
    _age_claim(task, execution)
    backend: Queue[int] = Queue()

    def finish() -> None:
        if finalizer == "exception":
            handle_task_error(task, execution, "old worker exception")
        else:
            update_task_status(task, execution, finalizer, result_data={"old": True}, error_message="old result")

    with ThreadPoolExecutor(max_workers=1) as executor:
        with transaction.atomic():
            current = Task.objects.select_for_update().get(pk=task.pk)
            future = executor.submit(_on_connection, finish, backend)
            _wait_for_database_lock(backend.get(timeout=5))
            UnifiedTaskScheduler()._fail_stuck_tasks()
            current.refresh_from_db()
            assert current.retry()
            retry_task, retry_execution = _claim_task(current.pk)
        future.result(timeout=10)

    retry_task.refresh_from_db()
    retry_execution.refresh_from_db()
    execution.refresh_from_db()
    assert retry_task.status == "running"
    assert retry_task.attempts == 2
    assert retry_task.result_data == {}
    assert retry_execution.status == "running"
    assert execution.status == "failed"


@pytest.mark.parametrize("winner", ["worker", "recovery"])
def test_cancelled_worker_and_recovery_preserve_the_first_execution_outcome(winner: str) -> None:
    """Both interleavings keep the Task cancelled and finalize the attempt once."""
    task, execution = _claimed_task()
    _age_claim(task, execution)
    assert task.cancel()
    backend: Queue[int] = Queue()

    def finish() -> None:
        update_task_status(task, execution, "completed", result_data={"winner": "worker"})

    def recover() -> None:
        UnifiedTaskScheduler()._fail_stuck_tasks()

    with ThreadPoolExecutor(max_workers=1) as executor:
        with transaction.atomic():
            Task.objects.select_for_update().get(pk=task.pk)
            loser = recover if winner == "worker" else finish
            future = executor.submit(_on_connection, loser, backend)
            _wait_for_database_lock(backend.get(timeout=5))
            (finish if winner == "worker" else recover)()
        future.result(timeout=10)

    task.refresh_from_db()
    execution.refresh_from_db()
    assert task.status == "cancelled"
    assert task.attempts == 1
    assert execution.status == ("completed" if winner == "worker" else "failed")
    assert execution.completed_at is not None
    if winner == "worker":
        assert execution.result_data == {"winner": "worker"}


def test_failed_dispatch_without_a_claim_cannot_fail_another_dispatch() -> None:
    """A rolled-back claim must not fail a different dispatch's successful claim."""
    task = Task.objects.create(name="Competing dispatches", function_name="hello_world")
    winning_claim: list[tuple[Task, TaskExecution]] = []

    def lose_claim(task_id: int) -> None:
        try:
            with patch("apps.tasks.models.TaskExecution.objects.create", side_effect=RuntimeError("claim failed")):
                _claim_task(task_id)
        except RuntimeError:
            winning_claim.append(_claim_task(task_id))
            raise
        pytest.fail("The injected claim failure did not occur")

    with patch("apps.tasks.tasks_system._claim_task", side_effect=lose_claim):
        result = execute_db_task(task_id=task.pk)

    assert result["status"] == "error"
    assert "claim failed" in result["error"]
    task.refresh_from_db()
    winner, execution = winning_claim[0]
    execution.refresh_from_db()
    assert task.status == "running"
    assert task.attempts == 1
    assert task.error_message == ""
    assert execution.status == "running"
    assert task.executions.count() == 1

    update_task_status(winner, execution, "completed")
    task.refresh_from_db()
    assert task.status == "completed"


def test_old_execution_error_preserves_a_pending_retry() -> None:
    """An execution-bearing late error is not a claimless pre-claim failure."""
    task, execution = _claimed_task()
    handle_task_error(task, execution, "original failure")
    assert task.retry()

    handle_task_error(task, execution, "late error")

    task.refresh_from_db()
    execution.refresh_from_db()
    assert task.status == "pending"
    assert task.attempts == 1
    assert task.error_message == ""
    assert execution.status == "failed"
    assert execution.error_message == "original failure"
    task, next_execution = _claim_task(task.pk)
    assert task.attempts == 2
    assert next_execution.pk != execution.pk


@pytest.mark.parametrize("parent_status", ["completed", "failed"])
@pytest.mark.parametrize("finalizer", ["completed", "exception"])
def test_terminal_parent_can_preserve_its_state_while_recording_a_running_attempt(
    parent_status: str, finalizer: str
) -> None:
    """Task and attempt outcomes are independent even when the parent is not cancelled."""
    task, execution = _claimed_task()
    Task.objects.filter(pk=task.pk).update(
        status=parent_status, completed_at=timezone.now(), result_data={"preserved": True}
    )

    if finalizer == "exception":
        handle_task_error(task, execution, "worker error")
    else:
        update_task_status(task, execution, "completed", result_data={"worker": True})

    task.refresh_from_db()
    execution.refresh_from_db()
    assert task.status == parent_status
    assert task.result_data == {"preserved": True}
    assert task.attempts == 1
    assert execution.status == ("failed" if finalizer == "exception" else "completed")
    assert execution.completed_at is not None
    if finalizer == "completed":
        assert execution.result_data == {"worker": True}


def test_recovery_samples_terminal_time_after_waiting_for_the_task_lock() -> None:
    """A pre-lock cutoff must not become a pre-attempt completion timestamp."""
    scan_time = timezone.now()
    execution_start = scan_time + timedelta(seconds=5)
    terminal_time = scan_time + timedelta(seconds=10)
    task = Task.objects.create(
        name="Slow claim transaction",
        function_name="hello_world",
        status="running",
        started_at=scan_time - timedelta(seconds=settings.TASK_TIMEOUT + 1),
    )
    fresh = Task.objects.create(
        name="Fresh at scan time",
        function_name="hello_world",
        status="running",
        started_at=scan_time - timedelta(seconds=settings.TASK_TIMEOUT - 1),
    )
    backend: Queue[int] = Queue()

    def recover() -> list[int]:
        return fail_stuck_tasks(Task.objects.all(), scan_time, settings.TASK_TIMEOUT)

    with (
        patch("apps.tasks.utils.timezone.now", return_value=terminal_time),
        ThreadPoolExecutor(max_workers=1) as executor,
    ):
        with transaction.atomic():
            Task.objects.select_for_update().get(pk=task.pk)
            future = executor.submit(_on_connection, recover, backend)
            _wait_for_database_lock(backend.get(timeout=5))
            with patch("django.utils.timezone.now", return_value=execution_start):
                execution = TaskExecution.objects.create(task=task, status="running")
        assert future.result(timeout=10) == [task.pk]

    task.refresh_from_db()
    execution.refresh_from_db()
    fresh.refresh_from_db()
    assert task.completed_at == task.modified == terminal_time
    assert execution.started_at == execution_start
    assert execution.completed_at == execution.modified == terminal_time
    assert execution.execution_time_seconds == pytest.approx(5)
    assert fresh.status == "running"


def test_claim_updates_modified_with_its_start_time() -> None:
    """Claiming is a lifecycle transition, not an invisible queryset update."""
    task = Task.objects.create(name="Claim timestamp", function_name="hello_world")
    old = timezone.now() - timedelta(days=2)
    Task.objects.filter(pk=task.pk).update(modified=old)

    claimed, _execution = _claim_task(task.pk)

    assert claimed.modified == claimed.started_at
    assert claimed.modified > old


def test_discarded_superseded_result_warns_without_logging_payload(caplog: pytest.LogCaptureFixture) -> None:
    """A result accepted by neither lifecycle row is visible without exposing its data."""
    task, execution = _claimed_task()
    handle_task_error(task, execution, "original attempt failed")
    assert task.retry()
    next_task, next_execution = _claim_task(task.pk)
    caplog.clear()
    marker = "payload content must not enter logs"

    with caplog.at_level(logging.INFO, logger="apps.tasks.utils"):
        update_task_status(task, execution, "completed", result_data={"private_result": marker})

    warnings = [record for record in caplog.records if record.levelno == logging.WARNING]
    assert len(warnings) == 1
    message = warnings[0].getMessage()
    assert "Discarded" in message
    assert f"task {task.pk}" in message
    assert f"execution {execution.pk}" in message
    assert marker not in caplog.text
    assert "private_result" not in caplog.text
    next_task.refresh_from_db()
    next_execution.refresh_from_db()
    assert next_task.status == next_execution.status == "running"
    assert next_task.result_data == {}


@pytest.mark.parametrize("parent_status", ["cancelled", "completed", "failed"])
def test_result_preserved_in_execution_does_not_warn(parent_status: str, caplog: pytest.LogCaptureFixture) -> None:
    """A rejected parent write is routine when its attempt still records the result."""
    task, execution = _claimed_task()
    Task.objects.filter(pk=task.pk).update(status=parent_status, completed_at=timezone.now())

    with caplog.at_level(logging.INFO, logger="apps.tasks.utils"):
        update_task_status(task, execution, "completed", result_data={"recorded": True})

    assert not [record for record in caplog.records if record.levelno >= logging.WARNING]
    assert any("Dropped stale" in record.getMessage() for record in caplog.records)
    task.refresh_from_db()
    execution.refresh_from_db()
    assert task.status == parent_status
    assert execution.status == "completed"
    assert execution.result_data == {"recorded": True}
