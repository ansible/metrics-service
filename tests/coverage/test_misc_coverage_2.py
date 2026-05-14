"""
Additional miscellaneous coverage tests for small uncovered areas.
"""

import decimal
from io import StringIO
from unittest.mock import MagicMock, patch

import pytest
from django.utils import timezone


# ---------------------------------------------------------------------------
# dashboard_reports/utils.py — sec2time
# ---------------------------------------------------------------------------
@pytest.mark.unit
def test_sec2time_minutes_only():
    from apps.dashboard_reports.utils import sec2time

    result = sec2time(150)
    assert "2min" in result
    assert "30sec" in result


@pytest.mark.unit
def test_sec2time_hours_minutes_seconds():
    from apps.dashboard_reports.utils import sec2time

    result = sec2time(3665)
    assert "1h" in result
    assert "1min" in result
    assert "5sec" in result


@pytest.mark.unit
def test_sec2time_zero():
    from apps.dashboard_reports.utils import sec2time

    result = sec2time(0)
    assert "0min" in result


@pytest.mark.unit
def test_sec2time_decimal():
    from apps.dashboard_reports.utils import sec2time

    result = sec2time(decimal.Decimal("90.5"))
    assert "1min" in result


# ---------------------------------------------------------------------------
# tasks/apps.py — coverage for uncovered app config methods
# ---------------------------------------------------------------------------
@pytest.mark.unit
def test_tasks_app_config_exists():
    from apps.tasks.apps import TasksConfig

    assert TasksConfig.name == "apps.tasks"


# ---------------------------------------------------------------------------
# management command _handle_task_create
# ---------------------------------------------------------------------------
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


@pytest.mark.unit
@pytest.mark.django_db
def test_handle_task_create_basic():
    cmd = get_cmd()
    cmd._handle_task_create({
        "name": "cmd_create_task",
        "function": "hello_world",
        "description": "test desc",
        "data": None,
        "scheduled_time": None,
        "user": None,
        "cron": None,
    })
    from apps.tasks.models import Task
    assert Task.objects.filter(name="cmd_create_task").exists()


@pytest.mark.unit
@pytest.mark.django_db
def test_handle_task_create_with_json_data():
    cmd = get_cmd()
    cmd._handle_task_create({
        "name": "json_data_task",
        "function": "hello_world",
        "description": "with data",
        "data": '{"key": "value"}',
        "scheduled_time": None,
        "user": None,
        "cron": None,
    })
    from apps.tasks.models import Task
    task = Task.objects.get(name="json_data_task")
    assert task.task_data == {"key": "value"}


@pytest.mark.unit
@pytest.mark.django_db
def test_handle_task_create_invalid_json():
    from django.core.management.base import CommandError

    cmd = get_cmd()
    with pytest.raises(CommandError, match="Invalid JSON"):
        cmd._handle_task_create({
            "name": "bad_json_task",
            "function": "hello_world",
            "description": "",
            "data": "not-json{",
            "scheduled_time": None,
            "user": None,
            "cron": None,
        })


@pytest.mark.unit
@pytest.mark.django_db
def test_handle_task_create_invalid_scheduled_time():
    from django.core.management.base import CommandError

    cmd = get_cmd()
    with pytest.raises(CommandError, match="Invalid scheduled time"):
        cmd._handle_task_create({
            "name": "bad_time_task",
            "function": "hello_world",
            "description": "",
            "data": None,
            "scheduled_time": "not-a-date",
            "user": None,
            "cron": None,
        })


@pytest.mark.unit
@pytest.mark.django_db
def test_handle_task_create_user_not_found():
    from django.core.management.base import CommandError

    cmd = get_cmd()
    with pytest.raises(CommandError, match="User.*not found"):
        cmd._handle_task_create({
            "name": "user_task",
            "function": "hello_world",
            "description": "",
            "data": None,
            "scheduled_time": None,
            "user": "nonexistent_user_xyz",
            "cron": None,
        })


@pytest.mark.unit
@pytest.mark.django_db
def test_handle_task_create_with_scheduled_time():
    cmd = get_cmd()
    cmd._handle_task_create({
        "name": "scheduled_task_cmd",
        "function": "hello_world",
        "description": "",
        "data": None,
        "scheduled_time": "2030-01-01 12:00:00",
        "user": None,
        "cron": None,
    })
    from apps.tasks.models import Task
    task = Task.objects.get(name="scheduled_task_cmd")
    assert task.scheduled_time is not None


# ---------------------------------------------------------------------------
# tasks/v1/serializers.py — cover some serializer classes
# ---------------------------------------------------------------------------
@pytest.mark.unit
def test_task_serializer_imports():
    from apps.tasks.v1.serializers import (
        TaskSerializer,
        TaskCreateSerializer,
        TaskListSerializer,
        TaskExecutionSerializer,
    )
    assert TaskSerializer is not None
    assert TaskCreateSerializer is not None
