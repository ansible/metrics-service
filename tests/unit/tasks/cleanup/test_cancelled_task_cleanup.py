"""Cancelled task retention must not remove the recurring schedule definition."""

from datetime import timedelta
from typing import Any

import pytest
from django.utils import timezone
from rest_framework.reverse import reverse
from rest_framework.test import APIClient

from apps.tasks.cleanup.cleanup_old_tasks import cleanup_old_tasks
from apps.tasks.models import Task

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def _old_cancelled_task(*, cron: str | None = None, legacy: bool = False, **kwargs: Any) -> Task:
    task = Task.objects.create(name="Cancelled history", function_name="hello_world", cron_expression=cron, **kwargs)
    assert task.cancel()
    old = timezone.now() - timedelta(days=40)
    Task.objects.filter(pk=task.pk).update(completed_at=None if legacy else old, modified=old)
    return task


@pytest.mark.parametrize("dry_run", [True, False])
@pytest.mark.parametrize("is_system", [True, False])
@pytest.mark.parametrize("child_cron", [None, ""])
def test_cleanup_api_keeps_cancelled_schedules_but_cleans_their_history(
    authenticated_client: APIClient, dry_run: bool, is_system: bool, child_cron: str | None
) -> None:
    """Neither user nor system recurring templates belong in task-history cleanup."""
    schedule = _old_cancelled_task(cron="0 * * * *", is_system_task=is_system)
    child = _old_cancelled_task(cron=child_cron, is_system_task=is_system)

    response = authenticated_client.post(
        reverse("tasks:v1:task-cleanup"), {"days": 30, "dry_run": dry_run}, format="json"
    )

    assert response.status_code == 200
    assert response.data["count"] == 1
    assert Task.objects.filter(pk=schedule.pk).exists()
    assert Task.objects.filter(pk=child.pk).exists() == dry_run
    if dry_run:
        assert [item["id"] for item in response.data["preview"]] == [child.pk]


@pytest.mark.parametrize("dry_run", [True, False])
@pytest.mark.parametrize("legacy", [True, False])
@pytest.mark.parametrize("cron", [None, "", "0 * * * *"])
def test_scheduled_cleanup_includes_cancelled_history_without_deleting_schedules(
    dry_run: bool, legacy: bool, cron: str | None
) -> None:
    """The existing modified fallback covers cancellations predating completed_at."""
    task = _old_cancelled_task(cron=cron, legacy=legacy)
    recurring = bool(cron)

    result = cleanup_old_tasks(days_old=30, dry_run=dry_run)

    assert result["tasks_found"] == (0 if recurring else 1)
    assert result["tasks_deleted"] == (0 if recurring or dry_run else 1)
    assert Task.objects.filter(pk=task.pk).exists() == (recurring or dry_run)


@pytest.mark.parametrize("legacy", [True, False])
def test_scheduled_cleanup_preserves_cancelled_oneshot_system_tasks(legacy: bool) -> None:
    """Task-group one-shots remain protected for every terminal status."""
    task = _old_cancelled_task(legacy=legacy, is_system_task=True)
    Task.objects.filter(pk=task.pk).update(name="initial_dashboard_collection")

    result = cleanup_old_tasks(days_old=30)

    assert result["tasks_deleted"] == 0
    assert Task.objects.filter(pk=task.pk).exists()


def test_scheduled_cleanup_can_explicitly_remove_a_cancelled_schedule() -> None:
    """Retain the existing deliberate opt-out of recurring-task protection."""
    task = _old_cancelled_task(cron="0 * * * *")

    result = cleanup_old_tasks(days_old=30, preserve_recurring=False)

    assert result["tasks_deleted"] == 1
    assert not Task.objects.filter(pk=task.pk).exists()


@pytest.mark.parametrize("legacy", [True, False])
def test_scheduled_cleanup_keeps_recent_cancelled_history(legacy: bool) -> None:
    """Prefer a known completion time, using modified only for legacy nulls."""
    task = _old_cancelled_task(legacy=legacy)
    recent = timezone.now() - timedelta(days=1)
    updates = {"modified": recent} if legacy else {"completed_at": recent}
    Task.objects.filter(pk=task.pk).update(**updates)

    result = cleanup_old_tasks(days_old=30)

    assert result["tasks_deleted"] == 0
    assert Task.objects.filter(pk=task.pk).exists()
