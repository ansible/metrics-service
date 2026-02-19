"""
Shared fixtures for tasks unit tests.

This module provides fixtures specific to the tasks app testing,
supplementing the global fixtures in tests/conftest.py.
"""

from datetime import timedelta
from unittest.mock import MagicMock

import pytest
from django.utils import timezone


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
def sample_dataframe():
    """Sample pandas DataFrame for testing collectors."""
    import pandas as pd

    return pd.DataFrame(
        {
            "id": [1, 2, 3],
            "name": ["test1", "test2", "test3"],
            "value": [10, 20, 30],
        }
    )


@pytest.fixture
def empty_dataframe():
    """Empty pandas DataFrame for testing edge cases."""
    import pandas as pd

    return pd.DataFrame()


@pytest.fixture
def mock_rollup_processor():
    """Mock rollup processor with prepare/base/merge methods."""
    processor = MagicMock()
    processor.prepare.return_value = MagicMock()  # Mock prepared dataframe
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
def mock_collector():
    """Mock collector instance with gather method."""
    collector = MagicMock()
    import pandas as pd

    collector.gather.return_value = pd.DataFrame({"test": [1, 2, 3]})
    return collector


@pytest.fixture
def mock_db_for_collectors():
    """Mock database connection for collectors (more specific than global mock_db_connection)."""
    return MagicMock()
