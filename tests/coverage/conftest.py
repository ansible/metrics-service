"""
Coverage-focused test fixtures supplementing tests/conftest.py.
"""

from contextlib import contextmanager
from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
from django.utils import timezone


@pytest.fixture
def mock_dispatcherd():
    """Patch dispatcherd.publish so no real broker connection is needed."""
    with patch("dispatcherd.publish.submit_task") as mock_submit:
        yield mock_submit


@pytest.fixture
def mock_dispatcherd_config():
    """Patch ensure_dispatcherd_configured to a no-op."""
    with patch("apps.tasks.dispatcherd_config.ensure_dispatcherd_configured"):
        yield


@pytest.fixture
def mock_lock_acquired():
    """Patch metrics_utility lock so it immediately yields True (acquired)."""

    @contextmanager
    def _fake_lock(key, wait=True, db=None):
        yield True

    with patch("metrics_utility.library.lock.lock", side_effect=_fake_lock):
        yield


@pytest.fixture
def mock_lock_not_acquired():
    """Patch metrics_utility lock so it immediately yields False (not acquired)."""

    @contextmanager
    def _fake_lock(key, wait=True, db=None):
        yield False

    with patch("metrics_utility.library.lock.lock", side_effect=_fake_lock):
        yield


@pytest.fixture
def mock_apscheduler():
    """Mock BackgroundScheduler so no real threads are spawned."""
    with patch("apps.tasks.cron_scheduler.BackgroundScheduler") as mock_cls:
        mock_instance = MagicMock()
        mock_instance.running = True
        mock_cls.return_value = mock_instance
        yield mock_instance


@pytest.fixture
@pytest.mark.django_db
def task_with_cron(db, user):
    """Create a recurring (cron-driven) Task."""
    from apps.tasks.models import Task

    return Task.objects.create(
        name="test_recurring",
        function_name="hello_world",
        cron_expression="0 * * * *",
        task_data={},
        status="pending",
        created_by=user,
    )


@pytest.fixture
@pytest.mark.django_db
def completed_task(db, user):
    """Create a Task(status='completed') backdated 10 days."""
    from apps.tasks.models import Task

    t = Task.objects.create(
        name="old_completed",
        function_name="hello_world",
        task_data={},
        status="completed",
        created_by=user,
    )
    Task.objects.filter(pk=t.pk).update(completed_at=timezone.now() - timedelta(days=10))
    t.refresh_from_db()
    return t


@pytest.fixture
@pytest.mark.django_db
def hourly_collection(db):
    """Create a HourlyMetricsCollection record."""
    from apps.tasks.models import HourlyMetricsCollection

    return HourlyMetricsCollection.objects.create(
        collector_type="unified_jobs",
        collection_timestamp=timezone.now().replace(minute=0, second=0, microsecond=0),
        raw_data={"test": "data"},
        status="collected",
    )
