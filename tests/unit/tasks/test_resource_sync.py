import uuid
from io import StringIO
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from ansible_base.rbac import permission_registry
from ansible_base.rbac.models import RoleDefinition
from ansible_base.resource_registry.models import Resource
from ansible_base.resource_registry.tasks.sync import AssignmentTuple
from django.apps import apps

from apps.core.models import Organization, User
from apps.tasks import tasks
from apps.tasks.simple import resource_sync


@pytest.mark.unit
def test_incomplete_assignment_fetch_still_syncs_resources_but_skips_assignments(monkeypatch):
    api_client = object()
    events = []
    executor = SimpleNamespace(run=Mock(), results={})
    reconcile = Mock()

    monkeypatch.setattr(resource_sync, "create_api_client", lambda: api_client)
    monkeypatch.setattr(
        resource_sync,
        "get_remote_assignments",
        lambda client: events.append("assignments") or SimpleNamespace(assignments=set(), is_complete=False),
    )
    monkeypatch.setattr(
        resource_sync,
        "SyncExecutor",
        Mock(side_effect=lambda **kwargs: events.append("resources") or executor),
    )
    monkeypatch.setattr(resource_sync, "_reconcile_assignments", reconcile)

    result = resource_sync.sync_resources_from_gateway()

    assert result["status"] == "error"
    executor.run.assert_called_once()
    assert events == ["resources", "assignments"]
    reconcile.assert_not_called()


@pytest.mark.unit
@pytest.mark.parametrize("status", ["error", "unavailable"])
def test_retryable_resource_sync_errors_skip_assignment_reconciliation(monkeypatch, status):
    api_client = object()
    executor = SimpleNamespace(run=Mock(), results={status: [object()]})
    reconcile = Mock()
    assignments = Mock()

    monkeypatch.setattr(resource_sync, "create_api_client", lambda: api_client)
    monkeypatch.setattr(
        resource_sync,
        "get_remote_assignments",
        assignments,
    )
    monkeypatch.setattr(resource_sync, "SyncExecutor", Mock(return_value=executor))
    monkeypatch.setattr(resource_sync, "_reconcile_assignments", reconcile)

    result = resource_sync.sync_resources_from_gateway()

    assert result["status"] == "error"
    executor.run.assert_called_once()
    assignments.assert_not_called()
    reconcile.assert_not_called()


@pytest.mark.unit
def test_complete_fetch_disables_executor_assignment_sync_and_reconciles_snapshot(monkeypatch):
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
def test_resource_conflicts_do_not_block_assignment_reconciliation(monkeypatch):
    api_client = object()
    executor = SimpleNamespace(run=Mock(), results={"conflict": [object()]})
    assignments = {AssignmentTuple("user-1", "org-1", "Organization Member", "user")}
    reconcile = Mock(return_value={"assignments_created": 1, "assignments_deleted": 0, "assignment_errors": 0})

    monkeypatch.setattr(resource_sync, "create_api_client", lambda: api_client)
    monkeypatch.setattr(
        resource_sync,
        "get_remote_assignments",
        lambda client: SimpleNamespace(assignments=assignments, is_complete=True),
    )
    monkeypatch.setattr(resource_sync, "SyncExecutor", Mock(return_value=executor))
    monkeypatch.setattr(resource_sync, "_reconcile_assignments", reconcile)

    result = resource_sync.sync_resources_from_gateway()

    assert result["status"] == "success"
    assert result["summary"]["conflict"] == 1
    reconcile.assert_called_once()
    assert reconcile.call_args.args[0] == assignments
    assert isinstance(reconcile.call_args.args[1], StringIO)


@pytest.mark.unit
def test_set_difference_reconciles_only_missing_and_stale_assignments(monkeypatch):
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
def test_failed_assignment_helper_is_counted_and_does_not_stop_other_changes(monkeypatch):
    stale = AssignmentTuple("user-2", "org-2", "Organization Admin", "user")
    missing = AssignmentTuple("user-3", "org-3", "Organization Member", "user")
    monkeypatch.setattr(resource_sync, "get_local_assignments", Mock(return_value={stale}))
    delete = Mock(return_value=False)
    create = Mock(return_value=True)
    monkeypatch.setattr(resource_sync, "delete_local_assignment", delete)
    monkeypatch.setattr(resource_sync, "create_local_assignment", create)
    stdout = StringIO()

    summary = resource_sync._reconcile_assignments({missing}, stdout)

    assert summary == {"assignments_created": 1, "assignments_deleted": 0, "assignment_errors": 1}
    delete.assert_called_once_with(stale)
    create.assert_called_once_with(missing)
    assert "FAILED to delete assignment user user-2 -> Organization Admin on org-2" in stdout.getvalue()
    assert "CREATED assignment user user-3 -> Organization Member on org-3" in stdout.getvalue()


@pytest.mark.unit
def test_assignment_helper_failures_leave_task_retryable(monkeypatch):
    api_client = object()
    executor = SimpleNamespace(run=Mock(), results={})
    assignments = {AssignmentTuple("user-1", "org-1", "Organization Member", "user")}

    monkeypatch.setattr(resource_sync, "create_api_client", lambda: api_client)
    monkeypatch.setattr(
        resource_sync,
        "get_remote_assignments",
        lambda client: SimpleNamespace(assignments=assignments, is_complete=True),
    )
    monkeypatch.setattr(resource_sync, "SyncExecutor", Mock(return_value=executor))
    monkeypatch.setattr(
        resource_sync,
        "_reconcile_assignments",
        Mock(return_value={"assignments_created": 0, "assignments_deleted": 0, "assignment_errors": 1}),
    )

    result = resource_sync.sync_resources_from_gateway()

    assert result["status"] == "error"
    assert result["summary"]["assignment_errors"] == 1


@pytest.mark.django_db
def test_pinned_dab_assignment_helpers_create_read_and_delete_assignment():
    permission_registry.create_managed_roles(apps)
    user = User.objects.create(username="resource-sync-dab-helper-user")
    organization = Organization.objects.create(name="Resource Sync DAB Helper Org")
    user_ansible_id = uuid.uuid4()
    organization_ansible_id = uuid.uuid4()
    user_resource = Resource.get_resource_for_object(user)
    user_resource.ansible_id = user_ansible_id
    user_resource.save(update_fields=["ansible_id"])
    organization_resource = Resource.get_resource_for_object(organization)
    organization_resource.ansible_id = organization_ansible_id
    organization_resource.save(update_fields=["ansible_id"])
    assignment = AssignmentTuple(
        str(user_ansible_id),
        str(organization_ansible_id),
        RoleDefinition.objects.get(name="Organization Member").name,
        "user",
    )

    assert resource_sync.create_local_assignment(assignment) is True
    assert assignment in resource_sync.get_local_assignments()
    assert resource_sync.delete_local_assignment(assignment) is True
    assert assignment not in resource_sync.get_local_assignments()


@pytest.mark.unit
def test_gateway_resource_sync_uses_task_lock():
    assert "sync_resources_from_gateway" in tasks.TASK_LOCKS
