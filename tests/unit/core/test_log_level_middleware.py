"""Unit tests for LogLevelMiddleware (AAP-79584)."""

import logging
from datetime import timedelta

import pytest
from django.http import HttpResponse
from django.test import RequestFactory, override_settings
from django.utils import timezone

from apps.core import logging_control
from apps.core.middleware.log_level import LogLevelMiddleware

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
def test_middleware_applies_override_before_view():
    logging_control.set_override("DEBUG", ttl_seconds=60)
    seen = {}

    def view(request):
        seen["level"] = logging.getLogger("apps").level
        return HttpResponse("ok")

    response = LogLevelMiddleware(view)(RequestFactory().get("/anything/"))

    assert response.status_code == 200
    assert response.content == b"ok"
    assert seen["level"] == logging.DEBUG


@pytest.mark.django_db
def test_middleware_does_not_raise_when_sync_fails(monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("database is down")

    monkeypatch.setattr("apps.core.middleware.log_level.sync_from_db", boom)

    response = LogLevelMiddleware(lambda request: HttpResponse("ok"))(RequestFactory().get("/anything/"))
    assert response.status_code == 200


@override_settings(RUNTIME_LOG_LEVEL_REFRESH_SECONDS=60)
@pytest.mark.django_db
def test_middleware_is_throttled(django_assert_num_queries):
    middleware = LogLevelMiddleware(lambda request: HttpResponse("ok"))
    request = RequestFactory().get("/anything/")
    with django_assert_num_queries(1):
        middleware(request)
    with django_assert_num_queries(0):
        middleware(request)


@pytest.mark.django_db
def test_middleware_reverts_expired_override():
    logging_control.apply_level("DEBUG")
    logging_control.set_override("DEBUG", ttl_seconds=60)
    # Expire it directly without going through the model's auto_now fields.
    from apps.core.models import RuntimeLogLevelOverride

    RuntimeLogLevelOverride.objects.update(expires_at=timezone.now() - timedelta(seconds=1))

    LogLevelMiddleware(lambda request: HttpResponse("ok"))(RequestFactory().get("/anything/"))

    assert logging_control._APPLIED_LEVEL is None
