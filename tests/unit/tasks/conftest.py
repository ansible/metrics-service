"""
Shared fixtures for tasks unit tests.

This module provides fixtures specific to the tasks app testing,
supplementing the global fixtures in tests/conftest.py.
"""

import logging
from datetime import timedelta
from unittest.mock import MagicMock

import pytest
from django.utils import timezone

from apps.core.logging_filters import RequestIdFilter

# Canonical request ID used by the trace-continuity tests. Asserting against a
# specific known UUID (never just "non-empty") is what makes those tests fail
# for the wrong reason — e.g. two records sharing an unrelated default —
# impossible.
TRACE_REQUEST_ID = "6f1d1c2a-1f0e-4f0b-9a3e-2b1c4d5e6f70"

# Loggers that emit during an API request and during a worker-side task run.
_TRACE_LOGGER_NAMES = ("apps", "apps.tasks", "apps.tasks.tasks_system", "apps.core")


@pytest.fixture
def trace_records():
    """
    Collect log records with the production request-id filter applied.

    Test settings replace logging with a NullHandler root, so production
    wiring is never exercised by default. This fixture mirrors it: a handler
    with ``apps.core.logging_filters.RequestIdFilter`` attached (filters are
    per-handler) on the loggers that emit on the request → worker path. The
    filter stamps ``record.request_id`` exactly as the console handler does in
    production, so assertions on it are assertions on production behaviour.
    """
    records: list[logging.LogRecord] = []

    class _Collector(logging.Handler):
        def emit(self, record):
            records.append(record)

    handler = _Collector(level=logging.DEBUG)
    handler.addFilter(RequestIdFilter())
    loggers = [logging.getLogger(name) for name in _TRACE_LOGGER_NAMES]
    saved = [(lg.level, lg.propagate) for lg in loggers]
    for lg in loggers:
        lg.addHandler(handler)
        lg.setLevel(logging.DEBUG)
        lg.propagate = False
    try:
        yield records
    finally:
        for lg, (level, propagate) in zip(loggers, saved, strict=True):
            lg.removeHandler(handler)
            lg.setLevel(level)
            lg.propagate = propagate


@pytest.fixture
def system_task(user):
    """Create a system task (is_system_task=True)."""
    from apps.tasks.models import Task

    return Task.objects.create(
        name="System Task",
        function_name="cleanup_old_tasks",
        task_data={},
        created_by=user,
        is_system_task=True,
    )


@pytest.fixture
def old_completed_task(user):
    """Create an old completed task for cleanup testing."""
    from apps.tasks.models import Task

    old_time = timezone.now() - timedelta(days=100)
    task = Task.objects.create(
        name="Old Completed Task",
        function_name="hello_world",
        task_data={},
        created_by=user,
        status="completed",
    )
    # Update completed_at and modified manually to simulate old task
    Task.objects.filter(id=task.id).update(completed_at=old_time, modified=old_time)
    task.refresh_from_db()
    return task


@pytest.fixture
def old_failed_task(user):
    """Create an old failed task for cleanup testing."""
    from apps.tasks.models import Task

    old_time = timezone.now() - timedelta(days=100)
    task = Task.objects.create(
        name="Old Failed Task",
        function_name="hello_world",
        task_data={},
        created_by=user,
        status="failed",
    )
    # Update completed_at and modified manually to simulate old task
    Task.objects.filter(id=task.id).update(completed_at=old_time, modified=old_time)
    task.refresh_from_db()
    return task


@pytest.fixture
def recent_task(user):
    """Create a recent task that shouldn't be cleaned up."""
    from apps.tasks.models import Task

    return Task.objects.create(
        name="Recent Task",
        function_name="hello_world",
        task_data={},
        created_by=user,
        status="completed",
    )


@pytest.fixture
def recurring_task(user):
    """Create a recurring task."""
    from apps.tasks.models import Task

    return Task.objects.create(
        name="Recurring Task",
        function_name="hello_world",
        task_data={},
        created_by=user,
        cron_expression="0 * * * *",  # Every hour
    )


@pytest.fixture
def pending_task(user):
    """Create a pending task."""
    from apps.tasks.models import Task

    return Task.objects.create(
        name="Pending Task",
        function_name="hello_world",
        task_data={},
        created_by=user,
        status="pending",
    )


@pytest.fixture
def running_task(user):
    """Create a running task."""
    from apps.tasks.models import Task

    return Task.objects.create(
        name="Running Task",
        function_name="hello_world",
        task_data={},
        created_by=user,
        status="running",
    )


@pytest.fixture
def mock_rollup_processor():
    """Mock rollup processor with prepare/base/merge methods."""
    processor = MagicMock()
    processor.prepare.return_value = MagicMock()  # Mock prepared data
    processor.base.return_value = {
        "json": {"total": 100, "count": 3},
        "rollup": {"aggregated_data": "test"},
    }
    processor.merge.return_value = {"merged_data": "test"}
    return processor


@pytest.fixture
def hourly_collection_factory(user):
    """Factory for creating HourlyMetricsCollection objects."""

    def _create_collection(**kwargs):
        from apps.tasks.models import HourlyMetricsCollection

        defaults = {
            "collector_type": "job_host_summary_service",
            "collection_timestamp": timezone.now() - timedelta(hours=1),
            "raw_data": {"test": "data"},
            "status": "collected",
            "collection_parameters": {"database": "awx"},
        }
        defaults.update(kwargs)
        return HourlyMetricsCollection.objects.create(**defaults)

    return _create_collection


@pytest.fixture
def daily_summary_factory(user):
    """Factory for creating DailyMetricsSummary objects."""

    def _create_summary(**kwargs):
        from apps.tasks.models import DailyMetricsSummary

        defaults = {
            "summary_date": timezone.now().date(),
            "status": "pending",
            "aggregated_metrics": {"test": "data"},
        }
        defaults.update(kwargs)
        return DailyMetricsSummary.objects.create(**defaults)

    return _create_summary


@pytest.fixture
def mock_db_for_collectors():
    """Mock database connection for collectors (more specific than global mock_db_connection)."""
    return MagicMock()
