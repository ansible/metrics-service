"""Periodic resource sync task — pulls users, orgs, teams and RBAC assignments from gateway."""

import logging

logger = logging.getLogger(__name__)


def sync_resources_from_gateway(execution_id: str, **kwargs) -> dict:
    """
    Sync all shared resources and RBAC role assignments from the gateway.

    Runs SyncExecutor with no resource type filter so organization and team
    objects are created before user assignments that reference them, avoiding
    DoesNotExist errors on object-scoped roles.

    Idempotent — safe to run on every schedule tick and on first boot.
    """
    from io import StringIO

    from ansible_base.resource_registry.tasks.sync import SyncExecutor

    stdout = StringIO()
    executor = SyncExecutor(stdout=stdout)

    try:
        executor.run()
    except Exception as exc:
        logger.error("resource sync failed: %s", exc, exc_info=True)
        return {"status": "error", "error": str(exc), "output": stdout.getvalue()}

    results = getattr(executor, "results", {})
    summary = {k: len(v) for k, v in results.items() if isinstance(v, list)}
    logger.info("resource sync complete: %s", summary)

    return {"status": "completed", "summary": summary, "output": stdout.getvalue()}
