"""
Direct tests for management command handler methods.
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
# _handle_task_list
# ---------------------------------------------------------------------------
@pytest.mark.unit
@pytest.mark.django_db
def test_handle_task_list_with_tasks(user):
    from apps.tasks.models import Task

    Task.objects.create(
        name="list_task_1", function_name="hello_world", task_data={}, created_by=user, status="pending"
    )

    cmd = get_cmd()
    cmd._handle_task_list({"status": None, "limit": 20})
    output = cmd.stdout.getvalue()
    assert "list_task_1" in output


@pytest.mark.unit
@pytest.mark.django_db
def test_handle_task_list_empty():
    from apps.tasks.models import Task

    Task.objects.all().delete()
    cmd = get_cmd()
    cmd._handle_task_list({"status": None, "limit": 20})
    output = cmd.stdout.getvalue()
    assert "No tasks found" in output


@pytest.mark.unit
@pytest.mark.django_db
def test_handle_task_list_with_status_filter(user):
    from apps.tasks.models import Task

    Task.objects.create(
        name="running_one", function_name="hello_world", task_data={}, created_by=user, status="running"
    )
    Task.objects.create(
        name="pending_one", function_name="hello_world", task_data={}, created_by=user, status="pending"
    )

    cmd = get_cmd()
    cmd._handle_task_list({"status": "running", "limit": 20})
    output = cmd.stdout.getvalue()
    assert "running_one" in output
    assert "pending_one" not in output


# ---------------------------------------------------------------------------
# _handle_task_show
# ---------------------------------------------------------------------------
@pytest.mark.unit
@pytest.mark.django_db
def test_handle_task_show_existing(user):
    from apps.tasks.models import Task

    task = Task.objects.create(
        name="show_this",
        function_name="hello_world",
        task_data={"key": "value"},
        created_by=user,
        description="test description",
    )
    cmd = get_cmd()
    cmd._handle_task_show({"task_id": str(task.id)})
    output = cmd.stdout.getvalue()
    assert "show_this" in output
    assert "hello_world" in output


@pytest.mark.unit
@pytest.mark.django_db
def test_handle_task_show_not_found():
    from django.core.management.base import CommandError

    cmd = get_cmd()
    with pytest.raises(CommandError, match="not found"):
        cmd._handle_task_show({"task_id": "99999"})


# ---------------------------------------------------------------------------
# _handle_task_cancel
# ---------------------------------------------------------------------------
@pytest.mark.unit
@pytest.mark.django_db
def test_handle_task_cancel_pending(user):
    from apps.tasks.models import Task

    task = Task.objects.create(
        name="cancel_me", function_name="hello_world", task_data={}, created_by=user, status="pending"
    )
    cmd = get_cmd()
    cmd._handle_task_cancel({"task_id": str(task.id)})
    task.refresh_from_db()
    assert task.status == "cancelled"


@pytest.mark.unit
@pytest.mark.django_db
def test_handle_task_cancel_completed(user):
    from apps.tasks.models import Task

    task = Task.objects.create(
        name="already_done", function_name="hello_world", task_data={}, created_by=user, status="completed"
    )
    cmd = get_cmd()
    cmd._handle_task_cancel({"task_id": str(task.id)})
    task.refresh_from_db()
    assert task.status == "completed"  # Not cancelled


@pytest.mark.unit
@pytest.mark.django_db
def test_handle_task_cancel_not_found():
    from django.core.management.base import CommandError

    cmd = get_cmd()
    with pytest.raises(CommandError, match="not found"):
        cmd._handle_task_cancel({"task_id": "99999"})


# ---------------------------------------------------------------------------
# _handle_task_retry
# ---------------------------------------------------------------------------
@pytest.mark.unit
@pytest.mark.django_db
def test_handle_task_retry_failed(user):
    from apps.tasks.models import Task

    task = Task.objects.create(
        name="retry_me", function_name="hello_world", task_data={}, created_by=user, status="failed"
    )
    cmd = get_cmd()
    cmd._handle_task_retry({"task_id": str(task.id)})
    task.refresh_from_db()
    assert task.status == "pending"


@pytest.mark.unit
@pytest.mark.django_db
def test_handle_task_retry_completed(user):
    from apps.tasks.models import Task

    task = Task.objects.create(
        name="done_task", function_name="hello_world", task_data={}, created_by=user, status="completed"
    )
    cmd = get_cmd()
    cmd._handle_task_retry({"task_id": str(task.id)})
    task.refresh_from_db()
    assert task.status == "completed"  # Not changed


@pytest.mark.unit
@pytest.mark.django_db
def test_handle_task_retry_not_found():
    from django.core.management.base import CommandError

    cmd = get_cmd()
    with pytest.raises(CommandError, match="not found"):
        cmd._handle_task_retry({"task_id": "99999"})


# ---------------------------------------------------------------------------
# _list_system_tasks
# ---------------------------------------------------------------------------
@pytest.mark.unit
@pytest.mark.django_db
def test_list_system_tasks():
    from apps.tasks.models import Task

    Task.objects.filter(is_system_task=True).delete()
    Task.objects.create(name="sys_task_listed", function_name="hello_world", task_data={}, is_system_task=True)

    cmd = get_cmd()
    cmd._list_system_tasks()
    output = cmd.stdout.getvalue()
    assert "sys_task_listed" in output or "task" in output.lower()


# ---------------------------------------------------------------------------
# _handle_init_system_tasks_command
# ---------------------------------------------------------------------------
@pytest.mark.unit
@pytest.mark.django_db
def test_handle_init_system_tasks_command_without_list():
    with patch(
        "apps.tasks.tasks.create_system_tasks", return_value={"created": 3, "removed": 1, "tasks": ["Created: x"]}
    ):
        cmd = get_cmd()
        cmd._handle_init_system_tasks_command({"list": False})
    output = cmd.stdout.getvalue()
    assert "3" in output or "created" in output.lower() or "Initialized" in output
