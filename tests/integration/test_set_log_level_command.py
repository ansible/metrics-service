"""Integration tests for runtime log level control (AAP-79584)."""

import logging
from datetime import timedelta
from io import StringIO

import pytest
from django.core.management import call_command
from django.utils import timezone

from apps.core import logging_control
from apps.core.models import RuntimeLogLevelOverride

pytestmark = pytest.mark.integration

MANAGED = ("ansible_base", "metrics_service", "django", "apps")


@pytest.fixture(autouse=True)
def restore_logging_state():
    saved = {name: logging.getLogger(name).level for name in MANAGED}
    logging_control._APPLIED_LEVEL = None
    logging_control._BASELINE_LEVELS.clear()
    logging_control.reset_throttle()
    logging_control.reset_process_started_at()
    logging_control.revert()
    logging_control._APPLIED_LEVEL = None
    logging_control._BASELINE_LEVELS.clear()
    yield
    for name, level in saved.items():
        logging.getLogger(name).setLevel(level)
    logging_control._APPLIED_LEVEL = None
    logging_control._BASELINE_LEVELS.clear()
    logging_control.reset_throttle()


@pytest.mark.django_db
def test_request_picks_up_override_after_command(client):
    call_command("set_log_level", "DEBUG", "--ttl", "60", stdout=StringIO())
    logging_control.reset_throttle()

    client.get("/ping/")

    assert logging.getLogger("apps").level == logging.DEBUG
    assert logging.getLogger("django").level == logging.DEBUG


@pytest.mark.django_db
def test_clear_restores_configured_levels_on_next_request(client):
    """--clear restores the level each logger was configured with, not LOG_LEVEL."""
    # A per-logger level that differs from LOG_LEVEL, as development.py does.
    logging.getLogger("django").setLevel(logging.WARNING)

    call_command("set_log_level", "DEBUG", "--ttl", "60", stdout=StringIO())
    logging_control.reset_throttle()
    client.get("/ping/")
    assert logging.getLogger("django").level == logging.DEBUG

    call_command("set_log_level", "--clear", stdout=StringIO())
    logging_control.reset_throttle()
    client.get("/ping/")

    assert logging_control._APPLIED_LEVEL is None
    assert logging.getLogger("django").level == logging.WARNING


@pytest.mark.django_db
def test_restart_ignores_stale_override(client):
    call_command("set_log_level", "DEBUG", "--ttl", "3600", stdout=StringIO())

    # Simulate this process having started after the override was written.
    RuntimeLogLevelOverride.objects.update(modified=timezone.now() - timedelta(minutes=30))
    logging_control.reset_process_started_at(timezone.now() - timedelta(minutes=5))
    logging_control.reset_throttle()

    before = logging.getLogger("apps").level
    client.get("/ping/")

    assert logging.getLogger("apps").level == before
    assert logging_control._APPLIED_LEVEL is None
