"""Unit tests for apps.core.logging_control (AAP-79584)."""

import logging
from datetime import timedelta

import pytest
from django.test import override_settings
from django.utils import timezone

from apps.core import logging_control
from apps.core.models import RuntimeLogLevelOverride

pytestmark = pytest.mark.unit

MANAGED = ("ansible_base", "metrics_service", "django", "apps")


@pytest.fixture(autouse=True)
def restore_logging_state():
    """Snapshot and restore global logger levels; reset module-level state."""
    saved = {name: logging.getLogger(name).level for name in MANAGED}
    logging_control._APPLIED_LEVEL = None
    logging_control.reset_throttle()
    logging_control.reset_process_started_at()
    logging_control.revert()
    logging_control._APPLIED_LEVEL = None
    yield
    for name, level in saved.items():
        logging.getLogger(name).setLevel(level)
    logging_control._APPLIED_LEVEL = None
    logging_control.reset_throttle()


@pytest.mark.django_db
def test_apply_level_sets_all_managed_loggers():
    applied = logging_control.apply_level("DEBUG")
    assert set(applied) == set(MANAGED)
    for name in MANAGED:
        assert logging.getLogger(name).level == logging.DEBUG


@pytest.mark.django_db
def test_revert_restores_baseline():
    logging_control.apply_level("DEBUG")
    logging_control.revert()
    for name in MANAGED:
        assert logging.getLogger(name).level == logging.getLevelNamesMapping()[logging_control.BASELINE_LEVEL]


@pytest.mark.django_db
@pytest.mark.parametrize("bad", ["TRACE", "", None, 10])
def test_invalid_level_raises_value_error(bad):
    with pytest.raises(ValueError):
        logging_control.apply_level(bad)


@pytest.mark.django_db
def test_managed_loggers_defaults_under_test_settings():
    # The test settings replace LOGGING and define no named loggers.
    assert logging_control.managed_loggers() == MANAGED


@pytest.mark.django_db
def test_sync_without_row_leaves_baseline():
    logging_control.sync_from_db(force=True)
    assert logging_control._APPLIED_LEVEL is None
    for name in MANAGED:
        assert logging.getLogger(name).level == logging.getLevelNamesMapping()[logging_control.BASELINE_LEVEL]


@pytest.mark.django_db
def test_sync_applies_live_row():
    logging_control.set_override("DEBUG", ttl_seconds=60)
    logging_control.sync_from_db(force=True)
    assert logging_control._APPLIED_LEVEL == "DEBUG"
    for name in MANAGED:
        assert logging.getLogger(name).level == logging.DEBUG


@pytest.mark.django_db
def test_sync_reverts_expired_row():
    logging_control.apply_level("DEBUG")
    RuntimeLogLevelOverride.objects.create(
        level="DEBUG",
        expires_at=timezone.now() - timedelta(seconds=1),
        set_by="test",
    )
    logging_control.sync_from_db(force=True)
    assert logging_control._APPLIED_LEVEL is None
    assert logging.getLogger("apps").level == logging.getLevelNamesMapping()[logging_control.BASELINE_LEVEL]


@pytest.mark.django_db
def test_process_start_semantics():
    logging_control.set_override("DEBUG", ttl_seconds=60)
    # Simulate an override written before this process started.
    old = timezone.now() - timedelta(minutes=10)
    RuntimeLogLevelOverride.objects.update(modified=old)
    logging_control.reset_process_started_at(timezone.now() - timedelta(minutes=1))

    logging_control.sync_from_db(respect_process_start=True, force=True)
    assert logging_control._APPLIED_LEVEL is None, "override from before process start must be ignored"

    logging_control.sync_from_db(respect_process_start=False, force=True)
    assert logging_control._APPLIED_LEVEL == "DEBUG"


@pytest.mark.django_db
def test_sync_swallows_database_errors(monkeypatch):
    def boom():
        raise RuntimeError("database is down")

    monkeypatch.setattr(logging_control, "get_active_override", boom)
    assert logging_control.sync_from_db(force=True) is None


@pytest.mark.django_db
@override_settings(RUNTIME_LOG_LEVEL_REFRESH_SECONDS=60)
def test_sync_is_throttled(django_assert_num_queries):
    logging_control.reset_throttle()
    with django_assert_num_queries(1):
        logging_control.sync_from_db(force=True)
    with django_assert_num_queries(0):
        logging_control.sync_from_db()


@pytest.mark.django_db
def test_set_and_clear_override():
    override = logging_control.set_override("WARNING", ttl_seconds=120, actor="test")
    assert override.pk == 1
    assert override.level == "WARNING"
    assert override.set_by == "test"
    assert RuntimeLogLevelOverride.objects.count() == 1

    assert logging_control.clear_override() == 1
    assert logging_control.get_active_override() is None


@pytest.mark.django_db
def test_set_override_rejects_bad_ttl():
    with pytest.raises(ValueError):
        logging_control.set_override("DEBUG", ttl_seconds=0)
    with pytest.raises(ValueError):
        logging_control.set_override("DEBUG", ttl_seconds=10**9)


@pytest.mark.django_db
def test_singleton_enforced_on_save():
    RuntimeLogLevelOverride.objects.create(level="DEBUG", expires_at=timezone.now() + timedelta(minutes=5), set_by="a")
    RuntimeLogLevelOverride.objects.create(level="INFO", expires_at=timezone.now() + timedelta(minutes=5), set_by="b")
    assert RuntimeLogLevelOverride.objects.count() == 1
    assert RuntimeLogLevelOverride.objects.get().level == "INFO"


@pytest.mark.django_db
def test_notify_dispatcherd_disabled_is_noop(settings):
    settings.DISPATCHERD_ENABLED = False
    assert logging_control.notify_dispatcherd("DEBUG") is None


@pytest.mark.django_db
def test_dispatcherd_main_sync_applies_live_override():
    """The dispatcherd main-process refresh applies an active override."""
    logging_control.set_override("DEBUG", ttl_seconds=60)
    logging_control.reset_throttle()

    logging_control.sync_dispatcherd_log_level()

    assert logging_control._APPLIED_LEVEL == "DEBUG"


@pytest.mark.django_db
def test_dispatcherd_main_sync_reverts_expired_override():
    """TTL expiry must reach the dispatcherd main process, which has no task boundary."""
    logging_control.apply_level("DEBUG")
    RuntimeLogLevelOverride.objects.create(
        level="DEBUG",
        expires_at=timezone.now() - timedelta(seconds=1),
        set_by="test",
    )
    logging_control.reset_throttle()

    logging_control.sync_dispatcherd_log_level()

    baseline = logging.getLevelNamesMapping()[logging_control.BASELINE_LEVEL]
    assert logging_control._APPLIED_LEVEL is None
    assert logging.getLogger("apps").level == baseline


@pytest.mark.django_db
def test_dispatcherd_main_sync_reverts_after_clear():
    """Clearing the row must reach the dispatcherd main process on its next refresh."""
    logging_control.set_override("DEBUG", ttl_seconds=60)
    logging_control.reset_throttle()
    logging_control.sync_dispatcherd_log_level()
    assert logging_control._APPLIED_LEVEL == "DEBUG"

    logging_control.clear_override()
    logging_control.reset_throttle()
    logging_control.sync_dispatcherd_log_level()

    assert logging_control._APPLIED_LEVEL is None
