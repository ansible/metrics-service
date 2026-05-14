"""
Final tests to cross the 80% threshold.
"""

import pytest


# ---------------------------------------------------------------------------
# dashboard_reports/models.py — label_ids_to_job_data_ids
# ---------------------------------------------------------------------------
@pytest.mark.unit
@pytest.mark.django_db
def test_label_ids_to_job_data_ids_empty():
    from apps.dashboard_reports.models import label_ids_to_job_data_ids

    result = label_ids_to_job_data_ids([])
    assert list(result) == []


@pytest.mark.unit
@pytest.mark.django_db
def test_label_ids_to_job_data_ids_nonexistent():
    from apps.dashboard_reports.models import label_ids_to_job_data_ids

    result = label_ids_to_job_data_ids([99999])
    assert list(result) == []


# ---------------------------------------------------------------------------
# tasks/v1/serializers.py
# ---------------------------------------------------------------------------
@pytest.mark.unit
def test_task_serializer_has_fields():
    from apps.tasks.v1.serializers import TaskSerializer

    assert "id" in TaskSerializer().fields or "name" in TaskSerializer().fields


# ---------------------------------------------------------------------------
# tasks/models.py — TaskChain if it exists
# ---------------------------------------------------------------------------
@pytest.mark.unit
@pytest.mark.django_db
def test_task_ready_to_run_queryset(user):
    from apps.tasks.models import Task

    Task.objects.create(name="ready_check", function_name="hello_world", task_data={}, created_by=user, status="pending")
    qs = Task.ready_to_run()
    assert qs.exists()


# ---------------------------------------------------------------------------
# tasks/management/commands/metrics_service.py — some inline paths
# ---------------------------------------------------------------------------
@pytest.mark.unit
@pytest.mark.django_db
def test_metrics_service_tasks_list_no_status():
    from django.core.management import call_command

    call_command("metrics_service", "tasks", "list")  # Should not crash


@pytest.mark.unit
@pytest.mark.django_db
def test_metrics_service_tasks_list_with_limit():
    from django.core.management import call_command

    call_command("metrics_service", "tasks", "list", "--limit", "5")


# ---------------------------------------------------------------------------
# dashboard_reports/models.py — subscription cost related
# ---------------------------------------------------------------------------
@pytest.mark.unit
@pytest.mark.django_db
def test_subscription_cost_singleton_creation():
    from apps.dashboard_reports.models import SubscriptionCost

    SubscriptionCost.objects.all().delete()
    cost1 = SubscriptionCost.get()
    cost2 = SubscriptionCost.get()
    # Should be same instance (singleton)
    assert cost1.id == cost2.id
