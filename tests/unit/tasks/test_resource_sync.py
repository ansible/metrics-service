from io import StringIO
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from ansible_base.resource_registry.tasks.sync import AssignmentTuple

from apps.tasks import tasks
from apps.tasks.simple import resource_sync


@pytest.mark.unit
def test_incomplete_assignment_fetch_fails_before_local_sync(monkeypatch):
    api_client = object()
    executor = Mock()
    reconcile = Mock()

    monkeypatch.setattr(resource_sync, "create_api_client", lambda: api_client)
    monkeypatch.setattr(
        resource_sync,
        "get_remote_assignments",
        lambda client: SimpleNamespace(assignments=set(), is_complete=False),
    )
    monkeypatch.setattr(resource_sync, "SyncExecutor", Mock(return_value=executor))
    monkeypatch.setattr(resource_sync, "_reconcile_assignments", reconcile)

    result = resource_sync.sync_resources_from_gateway()

    assert result["status"] == "error"
    executor.run.assert_not_called()
    reconcile.assert_not_called()


@pytest.mark.unit
def test_resource_sync_errors_skip_assignment_reconciliation(monkeypatch):
    api_client = object()
    executor = SimpleNamespace(run=Mock(), results={"error": [object()]})
    reconcile = Mock()

    monkeypatch.setattr(resource_sync, "create_api_client", lambda: api_client)
    monkeypatch.setattr(
        resource_sync,
        "get_remote_assignments",
        lambda client: SimpleNamespace(assignments=set(), is_complete=True),
    )
    monkeypatch.setattr(resource_sync, "SyncExecutor", Mock(return_value=executor))
    monkeypatch.setattr(resource_sync, "_reconcile_assignments", reconcile)

    result = resource_sync.sync_resources_from_gateway()

    assert result["status"] == "error"
    executor.run.assert_called_once()
    reconcile.assert_not_called()


@pytest.mark.unit
def test_complete_fetch_reconciles_idempotently_and_disables_executor_assignment_sync(monkeypatch):
    api_client = object()
    executor = SimpleNamespace(run=Mock(), results={"created": [object()]})
    sync_executor = Mock(return_value=executor)
    assignments = {AssignmentTuple("user-1", "org-1", "Organization Member", "user")}
    reconcile = Mock(return_value={"assignments_created": 0, "assignments_deleted": 0, "assignment_errors": 0})

    monkeypatch.setattr(resource_sync, "create_api_client", lambda: api_client)
    monkeypatch.setattr(
        resource_sync,
        "get_remote_assignments",
        lambda client: SimpleNamespace(assignments=assignments, is_complete=True),
    )
    monkeypatch.setattr(resource_sync, "SyncExecutor", sync_executor)
    monkeypatch.setattr(resource_sync, "_reconcile_assignments", reconcile)

    result = resource_sync.sync_resources_from_gateway()

    assert result["status"] == "success"
    assert sync_executor.call_args.kwargs["api_client"] is api_client
    assert sync_executor.call_args.kwargs["sync_assignments"] is False
    assert isinstance(sync_executor.call_args.kwargs["stdout"], StringIO)
    reconcile.assert_called_once()
    assert reconcile.call_args.args[0] == assignments


@pytest.mark.unit
def test_repeated_assignment_reconciliation_does_not_duplicate_rows(monkeypatch):
    shared = AssignmentTuple("user-1", "org-1", "Organization Member", "user")
    stale = AssignmentTuple("user-2", "org-2", "Organization Member", "user")
    missing = AssignmentTuple("user-3", "org-3", "Organization Member", "user")
    remote = {shared, missing}
    monkeypatch.setattr(resource_sync, "get_local_assignments", Mock(side_effect=[{shared, stale}, remote]))
    create = Mock(return_value=True)
    delete = Mock(return_value=True)
    monkeypatch.setattr(resource_sync, "create_local_assignment", create)
    monkeypatch.setattr(resource_sync, "delete_local_assignment", delete)

    first = resource_sync._reconcile_assignments(remote, StringIO())
    second = resource_sync._reconcile_assignments(remote, StringIO())

    assert first == {"assignments_created": 1, "assignments_deleted": 1, "assignment_errors": 0}
    assert second == {"assignments_created": 0, "assignments_deleted": 0, "assignment_errors": 0}
    create.assert_called_once_with(missing)
    delete.assert_called_once_with(stale)


@pytest.mark.unit
def test_gateway_resource_sync_uses_task_lock():
    assert "sync_resources_from_gateway" in tasks.TASK_LOCKS
