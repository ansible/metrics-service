"""One-time resource sync task — pulls users, orgs, teams and RBAC assignments from Gateway."""

import logging
from io import StringIO

from ansible_base.resource_registry.tasks.sync import (
    AssignmentTuple,
    SyncExecutor,
    create_api_client,
    create_local_assignment,
    delete_local_assignment,
    get_local_assignments,
    get_remote_assignments,
)

from ..utils import create_task_result

logger = logging.getLogger(__name__)


def _reconcile_assignments(remote_assignments: set[AssignmentTuple], stdout: StringIO) -> dict[str, int]:
    """Apply a complete Gateway assignment snapshot to the local RBAC tables."""
    local_assignments = get_local_assignments()
    to_delete = local_assignments - remote_assignments
    to_create = remote_assignments - local_assignments

    summary = {"assignments_created": 0, "assignments_deleted": 0, "assignment_errors": 0}

    for assignment in to_delete:
        if delete_local_assignment(assignment):
            summary["assignments_deleted"] += 1
            stdout.write(f"DELETED assignment {assignment.assignment_type} {assignment.actor_ansible_id}\n")
        else:
            summary["assignment_errors"] += 1

    for assignment in to_create:
        if create_local_assignment(assignment):
            summary["assignments_created"] += 1
            stdout.write(f"CREATED assignment {assignment.assignment_type} {assignment.actor_ansible_id}\n")
        else:
            summary["assignment_errors"] += 1

    return summary


def sync_resources_from_gateway(**kwargs) -> dict:
    """
    Sync shared resources and complete RBAC role-assignment snapshots from Gateway.

    Fetch assignments completely before reconciling them. DAB reports when assignment
    pagination is incomplete but otherwise treats that result as a partial sync, so
    assignment syncing is disabled in SyncExecutor to let this task retry incomplete
    snapshots without applying assignment changes.
    """
    stdout = StringIO()

    try:
        api_client = create_api_client()
        remote_result = get_remote_assignments(api_client)
        if not remote_result.is_complete:
            error = "Gateway role-assignment fetch was incomplete; no local assignment changes were applied."
            logger.warning(error)
            stdout.write(error)
            return create_task_result("error", data={"output": stdout.getvalue()}, error=error)

        executor = SyncExecutor(api_client=api_client, sync_assignments=False, stdout=stdout)
        executor.run()
    except Exception as exc:
        logger.error("resource sync failed: %s", exc, exc_info=True)
        return create_task_result("error", data={"output": stdout.getvalue()}, error=str(exc))

    results = getattr(executor, "results", {})
    summary = {key: len(value) for key, value in results.items() if isinstance(value, list)}
    resource_errors = sum(len(results.get(status, [])) for status in ("error", "unavailable", "conflict"))
    if resource_errors:
        error = f"Resource sync completed with {resource_errors} errors; assignments were not reconciled."
        logger.error(error)
        return create_task_result("error", data={"summary": summary, "output": stdout.getvalue()}, error=error)

    try:
        assignment_summary = _reconcile_assignments(remote_result.assignments, stdout)
    except Exception as exc:
        logger.error("role assignment reconciliation failed: %s", exc, exc_info=True)
        return create_task_result("error", data={"summary": summary, "output": stdout.getvalue()}, error=str(exc))

    summary.update(assignment_summary)
    if assignment_summary["assignment_errors"]:
        error = f"Role assignment reconciliation had {assignment_summary['assignment_errors']} errors."
        logger.error(error)
        return create_task_result("error", data={"summary": summary, "output": stdout.getvalue()}, error=error)

    logger.info("resource sync complete: %s", summary)
    return create_task_result("success", {"summary": summary, "output": stdout.getvalue()})
