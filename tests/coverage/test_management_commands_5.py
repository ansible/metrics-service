"""
Tests for remaining uncovered management command methods.
"""

from io import StringIO
from unittest.mock import MagicMock, patch

import pytest


def get_cmd():
    from apps.tasks.management.commands.metrics_service import Command
    from apps.tasks.services.output_formatter import OutputFormatter

    cmd = Command()
    cmd.stdout = StringIO()
    mock_style = MagicMock()
    mock_style.SUCCESS.side_effect = lambda msg: msg
    mock_style.ERROR.side_effect = lambda msg: msg
    mock_style.WARNING.side_effect = lambda msg: msg
    cmd.style = mock_style
    cmd.output = OutputFormatter(stdout=cmd.stdout, style=cmd.style)
    return cmd


# ---------------------------------------------------------------------------
# _display_startup_message
# ---------------------------------------------------------------------------
@pytest.mark.unit
def test_display_startup_message():
    cmd = get_cmd()
    config = {
        "host": "127.0.0.1",
        "port": "8000",
        "gunicorn_workers": 4,
        "dispatcher_workers": 2,
    }
    cmd._display_startup_message(config)
    output = cmd.stdout.getvalue()
    assert "127.0.0.1" in output
    assert "8000" in output


# ---------------------------------------------------------------------------
# _build_service_commands
# ---------------------------------------------------------------------------
@pytest.mark.unit
def test_build_service_commands_returns_three_commands():
    import sys

    cmd = get_cmd()
    config = {
        "host": "0.0.0.0",
        "port": "8000",
        "gunicorn_workers": 4,
        "dispatcher_workers": 2,
        "timeout": 3600,
        "max_tasks": 100,
        "log_level": "INFO",
        "check_interval": 60,
    }
    commands = cmd._build_service_commands(sys.argv[0], config)
    assert len(commands) == 3  # Django, Dispatcher, Scheduler


# ---------------------------------------------------------------------------
# _setup_signal_handlers_for_processes
# ---------------------------------------------------------------------------
@pytest.mark.unit
def test_setup_signal_handlers():
    cmd = get_cmd()
    processes = []
    # Should not raise
    cmd._setup_signal_handlers_for_processes(processes)


# ---------------------------------------------------------------------------
# _handle_keyboard_interrupt
# ---------------------------------------------------------------------------
@pytest.mark.unit
def test_handle_keyboard_interrupt():
    cmd = get_cmd()
    mock_proc = MagicMock()
    mock_proc.poll.return_value = None

    # Should not raise
    cmd._handle_keyboard_interrupt([mock_proc])
    mock_proc.terminate.assert_called()


# ---------------------------------------------------------------------------
# _handle_startup_error
# ---------------------------------------------------------------------------
@pytest.mark.unit
def test_handle_startup_error():
    cmd = get_cmd()
    mock_proc = MagicMock()
    mock_proc.poll.return_value = None

    with pytest.raises(SystemExit):
        cmd._handle_startup_error([mock_proc], Exception("test error"))
    output = cmd.stdout.getvalue()
    assert "error" in output.lower() or "test error" in output


# ---------------------------------------------------------------------------
# _handle_init_system_tasks_command with list=True
# ---------------------------------------------------------------------------
@pytest.mark.unit
@pytest.mark.django_db
def test_handle_init_system_tasks_with_list_true(user):
    from apps.tasks.models import Task

    Task.objects.filter(is_system_task=True).delete()
    Task.objects.create(name="sys_listed", function_name="hello_world", task_data={}, is_system_task=True)

    with patch(
        "apps.tasks.tasks.create_system_tasks", return_value={"created": 1, "removed": 0, "tasks": ["Created: x"]}
    ):
        cmd = get_cmd()
        cmd._handle_init_system_tasks_command({"list": True})

    output = cmd.stdout.getvalue()
    assert "sys_listed" in output or "task" in output.lower()


# ---------------------------------------------------------------------------
# Tasks model - TaskExecution and HourlyMetricsCollection str reps
# ---------------------------------------------------------------------------
@pytest.mark.unit
@pytest.mark.django_db
def test_task_str_representation(user):
    from apps.tasks.models import Task

    task = Task.objects.create(name="str_rep_task", function_name="hello_world", task_data={}, created_by=user)
    assert "str_rep_task" in str(task)


@pytest.mark.unit
@pytest.mark.django_db
def test_task_execution_str_representation(user):
    from apps.tasks.models import Task, TaskExecution

    task = Task.objects.create(name="exec_str_task", function_name="hello_world", task_data={}, created_by=user)
    execution = TaskExecution.objects.create(task=task, status="running")
    assert "exec_str_task" in str(execution)


@pytest.mark.unit
@pytest.mark.django_db
def test_hourly_collection_str_representation():
    from django.utils import timezone

    from apps.tasks.models import HourlyMetricsCollection

    coll = HourlyMetricsCollection.objects.create(
        collector_type="unified_jobs",
        collection_timestamp=timezone.now().replace(minute=0, second=0, microsecond=0)
        - __import__("datetime").timedelta(hours=4),
        raw_data={},
        status="collected",
    )
    assert "unified" in str(coll).lower() or "Unified" in str(coll)
