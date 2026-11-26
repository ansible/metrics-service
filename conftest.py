"""Repo-wide pytest fixtures shared by tests/ and apps/*/tests/."""

import uuid

import pytest

from apps.tasks.task_groups import clear_feature_flag_cache


@pytest.fixture(autouse=True)
def _clear_caches(monkeypatch):
    """Ensure TTL caches do not leak between tests.

    Tests that mutate Setting via .update() expect immediate visibility;
    disable the flag TTL cache in tests so DB writes are observed instantly.
    """
    import apps.tasks.task_groups as tg

    from apps.tasks.cron_scheduler import clear_awx_ready_cache

    monkeypatch.setattr(tg, "_FLAG_CACHE_TTL_SECONDS", 0)
    clear_feature_flag_cache()
    clear_awx_ready_cache()
    yield
    clear_feature_flag_cache()
    clear_awx_ready_cache()


@pytest.fixture
def rando(db):
    """Create a user with no permissions."""
    from django.contrib.auth import get_user_model

    return get_user_model().objects.create(username=f"rando-{uuid.uuid4().hex[:8]}")


@pytest.fixture
def platform_auditor(db, rando):
    """Assign the Platform Auditor global role to rando and return the user."""
    from ansible_base.rbac.models import RoleDefinition

    RoleDefinition.objects.get(name="Platform Auditor").give_global_permission(rando)
    return rando
