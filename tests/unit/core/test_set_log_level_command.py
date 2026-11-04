"""Unit tests for the set_log_level management command (AAP-79584)."""

import logging
from datetime import timedelta
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone

from apps.core import logging_control
from apps.core.models import RuntimeLogLevelOverride

pytestmark = pytest.mark.unit

MANAGED = ("ansible_base", "metrics_service", "django", "apps")


@pytest.fixture(autouse=True)
def restore_logging_state():
    saved = {name: logging.getLogger(name).level for name in MANAGED}
    logging_control._APPLIED_LEVEL = None
    logging_control.reset_throttle()
    logging_control.reset_process_started_at()
    yield
    for name, level in saved.items():
        logging.getLogger(name).setLevel(level)
    logging_control._APPLIED_LEVEL = None
    logging_control.reset_throttle()


@pytest.mark.django_db
def test_set_level_creates_row():
    out = StringIO()
    call_command("set_log_level", "DEBUG", "--ttl", "60", stdout=out)

    override = RuntimeLogLevelOverride.objects.get(pk=1)
    assert override.level == "DEBUG"
    assert override.set_by.startswith("cli:")
    assert override.expires_at > timezone.now() + timedelta(seconds=30)
    assert "Log level set to DEBUG" in out.getvalue()


@pytest.mark.django_db
def test_ttl_zero_raises_command_error():
    with pytest.raises(CommandError):
        call_command("set_log_level", "DEBUG", "--ttl", "0")


@pytest.mark.django_db
def test_ttl_above_max_raises_command_error(settings):
    settings.RUNTIME_LOG_LEVEL_MAX_TTL = 10
    with pytest.raises(CommandError):
        call_command("set_log_level", "DEBUG", "--ttl", "11")


@pytest.mark.django_db
def test_show_without_override():
    out = StringIO()
    call_command("set_log_level", "--show", stdout=out)
    assert "No override set" in out.getvalue()


@pytest.mark.django_db
def test_show_active_override():
    logging_control.set_override("WARNING", ttl_seconds=60, actor="test")
    out = StringIO()
    call_command("set_log_level", "--show", stdout=out)
    text = out.getvalue()
    assert "level=WARNING" in text
    assert "(active)" in text


@pytest.mark.django_db
def test_clear_removes_row():
    logging_control.set_override("DEBUG", ttl_seconds=60)
    out = StringIO()
    call_command("set_log_level", "--clear", stdout=out)
    assert RuntimeLogLevelOverride.objects.count() == 0
    assert "cleared" in out.getvalue()


@pytest.mark.django_db
def test_clear_when_none():
    out = StringIO()
    call_command("set_log_level", "--clear", stdout=out)
    assert "No runtime log level override" in out.getvalue()


@pytest.mark.django_db
def test_local_applies_to_command_process():
    call_command("set_log_level", "DEBUG", "--local")
    for name in MANAGED:
        assert logging.getLogger(name).level == logging.DEBUG


@pytest.mark.django_db
def test_show_and_clear_mutually_exclusive():
    with pytest.raises(CommandError):
        call_command("set_log_level", "--show", "--clear")


@pytest.mark.django_db
def test_level_required_without_show_or_clear():
    with pytest.raises(CommandError):
        call_command("set_log_level")


@pytest.mark.django_db
def test_command_succeeds_when_dispatcherd_unavailable(settings):
    settings.DISPATCHERD_ENABLED = False
    out = StringIO()
    call_command("set_log_level", "INFO", stdout=out)
    assert RuntimeLogLevelOverride.objects.get(pk=1).level == "INFO"


@pytest.mark.django_db
def test_unified_metrics_service_command_delegates(settings):
    """`metrics-service set-log-level` reaches the Django command via the unified command."""
    settings.DISPATCHERD_ENABLED = False
    out = StringIO()
    call_command("metrics_service", "set-log-level", "DEBUG", "--ttl", "60", stdout=out)
    assert RuntimeLogLevelOverride.objects.get(pk=1).level == "DEBUG"
    assert "Log level set to DEBUG" in out.getvalue()


@pytest.mark.django_db
def test_clear_notifies_dispatcherd_with_baseline(monkeypatch):
    """--clear must tell dispatcherd to restore its main-process logger."""
    notified = []
    monkeypatch.setattr(logging_control, "notify_dispatcherd", lambda level: notified.append(level))
    logging_control.set_override("DEBUG", ttl_seconds=60)

    call_command("set_log_level", "--clear", stdout=StringIO())

    assert notified == [logging_control.BASELINE_LEVEL]
