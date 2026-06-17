"""
Tests for TEST_FAKE_TASKS env-var branches in task_groups.py and tasks.py.

Both modules contain module-level conditional imports/registrations that only
execute when TEST_FAKE_TASKS=true. These tests force a module reload with the
env var set to exercise those branches in CI where the env var is absent.
"""

import importlib
import os
import sys
from unittest.mock import patch

import pytest


def _reload_module(dotted_name: str):
    """Remove a module from sys.modules and reimport it."""
    sys.modules.pop(dotted_name, None)
    return importlib.import_module(dotted_name)


# ---------------------------------------------------------------------------
# task_groups.py — FAKE_TASKS_GROUP appended when TEST_FAKE_TASKS=true
# ---------------------------------------------------------------------------
@pytest.mark.unit
def test_task_groups_includes_fake_group_when_env_set():
    """TASK_GROUPS contains the fake_tasks group when TEST_FAKE_TASKS=true."""
    with patch.dict(os.environ, {"TEST_FAKE_TASKS": "true"}):
        tg = _reload_module("apps.tasks.task_groups")

    try:
        assert any(g.name == "fake_tasks" for g in tg.TASK_GROUPS)
    finally:
        # Restore module to its normal (env-var-absent) state
        _reload_module("apps.tasks.task_groups")


@pytest.mark.unit
def test_task_groups_excludes_fake_group_when_env_unset():
    """TASK_GROUPS does NOT contain the fake_tasks group when TEST_FAKE_TASKS is absent."""
    env = {k: v for k, v in os.environ.items() if k != "TEST_FAKE_TASKS"}
    with patch.dict(os.environ, env, clear=True):
        tg = _reload_module("apps.tasks.task_groups")

    try:
        assert not any(g.name == "fake_tasks" for g in tg.TASK_GROUPS)
    finally:
        _reload_module("apps.tasks.task_groups")


# ---------------------------------------------------------------------------
# tasks.py — fake_hourly_collector registered when TEST_FAKE_TASKS=true
# ---------------------------------------------------------------------------
@pytest.mark.unit
def test_tasks_registers_fake_collector_when_env_set():
    """TASK_FUNCTIONS and TASK_LOCKS include fake_hourly_collector when TEST_FAKE_TASKS=true."""
    with patch.dict(os.environ, {"TEST_FAKE_TASKS": "true"}):
        # task_groups must also be reloaded so the FAKE_TASKS_GROUP import succeeds
        _reload_module("apps.tasks.task_groups")
        tasks_mod = _reload_module("apps.tasks.tasks")

    try:
        assert "fake_hourly_collector" in tasks_mod.TASK_FUNCTIONS
        assert "fake_hourly_collector" in tasks_mod.TASK_LOCKS
    finally:
        _reload_module("apps.tasks.task_groups")
        _reload_module("apps.tasks.tasks")


@pytest.mark.unit
def test_tasks_excludes_fake_collector_when_env_unset():
    """TASK_FUNCTIONS does NOT include fake_hourly_collector when TEST_FAKE_TASKS is absent."""
    env = {k: v for k, v in os.environ.items() if k != "TEST_FAKE_TASKS"}
    with patch.dict(os.environ, env, clear=True):
        _reload_module("apps.tasks.task_groups")
        tasks_mod = _reload_module("apps.tasks.tasks")

    try:
        assert "fake_hourly_collector" not in tasks_mod.TASK_FUNCTIONS
        assert "fake_hourly_collector" not in tasks_mod.TASK_LOCKS
    finally:
        _reload_module("apps.tasks.task_groups")
        _reload_module("apps.tasks.tasks")
