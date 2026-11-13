"""
Regression guards for the request-ID settings wiring.

These assert on the *resolved* Django settings and on the post-hook behaviour.
They deliberately avoid reading ``metrics_service/settings.py`` (a
framework-managed file) or asserting on its source text: the wiring lives in
``apps/settings/defaults.py`` and must survive the test-mode ``LOGGING``
override in ``apps/settings/test.py``.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from django.conf import settings

from apps.settings.defaults import (
    _DAB_LOG_REQUEST_MIDDLEWARE,
    _REQUEST_ID_MIDDLEWARE,
    insert_request_id_middleware,
    use_project_request_id_filter,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
PROJECT_FILTER = "apps.core.logging_filters.RequestIdFilter"


class _SettingsStub:
    """Minimal stand-in for the Dynaconf instance handed to a post hook."""

    def __init__(self, **values):
        self._values = values

    def get(self, key, default=None):
        return self._values.get(key, default)


@pytest.mark.unit
class TestMiddlewareOrdering:
    """RequestIdMiddleware must wrap DAB's logging middlewares, not the reverse."""

    def test_is_registered_exactly_once(self):
        assert list(settings.MIDDLEWARE).count(_REQUEST_ID_MIDDLEWARE) == 1

    def test_sits_immediately_outside_the_dab_request_logger(self):
        middleware = list(settings.MIDDLEWARE)
        index = middleware.index(_REQUEST_ID_MIDDLEWARE)

        # Earlier in MIDDLEWARE == outer == the contextvar is already bound when
        # the following middleware handles the request / logs a traceback.
        assert middleware[index + 1] == _DAB_LOG_REQUEST_MIDDLEWARE
        assert index < middleware.index("ansible_base.lib.middleware.logging.LogTracebackMiddleware")

    def test_hook_is_idempotent(self):
        middleware = list(settings.MIDDLEWARE)

        assert insert_request_id_middleware(_SettingsStub(MIDDLEWARE=middleware)) == {}


@pytest.mark.unit
class TestRequestIdFilterWiring:
    """The project filter is selected wherever a request_id filter is defined."""

    def test_hook_selects_project_filter(self):
        log_cfg = {
            "filters": {"request_id": {"()": "ansible_base.lib.logging.filters.RequestIdFilter"}},
            "handlers": {"console": {"class": "logging.StreamHandler", "filters": ["request_id"]}},
        }

        result = use_project_request_id_filter(_SettingsStub(LOGGING=log_cfg))

        assert result["LOGGING"]["filters"]["request_id"]["()"] == PROJECT_FILTER
        # The hook must not mutate the caller's mapping.
        assert log_cfg["filters"]["request_id"]["()"] == "ansible_base.lib.logging.filters.RequestIdFilter"

    def test_hook_is_a_noop_when_the_filter_is_absent(self):
        """Test mode replaces LOGGING wholesale, so no filter may be injected."""
        # Mirrors apps/settings/test.py: a null handler and no ``filters`` block.
        test_mode_logging = {
            "version": 1,
            "disable_existing_loggers": False,
            "handlers": {"null": {"class": "logging.NullHandler"}},
            "root": {"handlers": ["null"]},
        }

        assert use_project_request_id_filter(_SettingsStub(LOGGING=test_mode_logging)) == {}

    def test_development_settings_resolve_to_the_project_filter(self):
        """Load the real settings outside test mode and inspect the result."""
        env = {
            **os.environ,
            "DJANGO_SETTINGS_MODULE": "metrics_service.settings",
            "METRICS_SERVICE_MODE": "development",
        }
        env.pop("METRICS_SERVICE_LOG_FORMAT", None)
        script = (
            "import django; django.setup();"
            "from django.conf import settings as s;"
            "print(s.LOGGING['filters']['request_id']['()']);"
            "print(','.join(s.LOGGING['handlers']['console']['filters']))"
        )

        completed = subprocess.run(
            [sys.executable, "-c", script],
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )

        filter_class, console_filters = completed.stdout.split()
        assert filter_class == PROJECT_FILTER
        assert console_filters == "request_id"
