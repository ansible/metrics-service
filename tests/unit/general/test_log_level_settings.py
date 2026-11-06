"""Unit tests that the 'apps' logger honors METRICS_SERVICE_LOG_LEVEL (ES-SUP-2).

`metrics_service/settings.py` is framework-owned and hard-codes the `apps`
logger at INFO, so the override lives in `apps/settings/defaults.py` as the
`apps_logger_follows_log_level` post-hook. These tests exercise that hook
against the LOGGING/LOG_LEVEL expressions taken from the framework file, which
is the wiring a real process ends up with (the hook runs after every settings
file and after environment variables are loaded).

The LOG_LEVEL parsing tests stay AST-based: they describe the protected
framework file, which cannot be imported in isolation.
"""

import ast
import os
from pathlib import Path
from unittest import mock

import pytest

from apps.settings.defaults import apps_logger_follows_log_level

pytestmark = pytest.mark.unit

SETTINGS_PATH = Path(__file__).resolve().parents[3] / "metrics_service" / "settings.py"
LOGGERS = ("ansible_base", "metrics_service", "django", "apps", "")


def _assignment(name: str) -> ast.expr:
    """Return the value expression of the top-level `name = ...` assignment."""
    tree = ast.parse(SETTINGS_PATH.read_text())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
            return node.value
    raise AssertionError(f"no top-level assignment to {name!r} in {SETTINGS_PATH}")


def _evaluate_log_level(env: dict[str, str]) -> str:
    with mock.patch.dict(os.environ, env, clear=True):
        return eval(  # noqa: S307 - evaluated against our own settings source
            compile(ast.Expression(_assignment("LOG_LEVEL")), str(SETTINGS_PATH), "eval"),
            {"os": os},
        )


def _evaluate_logging(log_level: str) -> dict:
    return eval(  # noqa: S307 - evaluated against our own settings source
        compile(ast.Expression(_assignment("LOGGING")), str(SETTINGS_PATH), "eval"),
        {"LOG_LEVEL": log_level},
    )


class TestLogLevelSettings:
    """ES-SUP-2: the application log level must be controlled by one environment variable."""

    def test_log_level_reads_env_var(self):
        assert _evaluate_log_level({"METRICS_SERVICE_LOG_LEVEL": "DEBUG"}) == "DEBUG"

    def test_log_level_is_uppercased(self):
        assert _evaluate_log_level({"METRICS_SERVICE_LOG_LEVEL": "warning"}) == "WARNING"

    def test_log_level_defaults_to_info(self):
        assert _evaluate_log_level({}) == "INFO"

    def test_framework_file_does_not_hardcode_apps_logger_to_log_level(self):
        """Regression guard: the protected file must keep the framework default."""
        assert _evaluate_logging("DEBUG")["loggers"]["apps"]["level"] == "INFO"


class TestAppsLoggerHook:
    """The post-hook that makes the 'apps' logger follow LOG_LEVEL."""

    @pytest.mark.parametrize("level", ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"])
    def test_all_loggers_follow_log_level_after_hook(self, level):
        """Every configured logger resolves to LOG_LEVEL once the hook has run."""
        merged = apps_logger_follows_log_level({"LOGGING": _evaluate_logging(level), "LOG_LEVEL": level})
        for name in LOGGERS:
            assert merged["LOGGING"]["loggers"][name]["level"] == level, (
                f"logger {name!r} does not honor METRICS_SERVICE_LOG_LEVEL"
            )

    def test_hook_uppercases_lowercase_env_value(self):
        """METRICS_SERVICE_LOG_LEVEL=warning must not reach logging._checkLevel(raw)."""
        cfg = apps_logger_follows_log_level(
            {"LOGGING": {"loggers": {"apps": {"level": "INFO"}}}, "LOG_LEVEL": "warning"}
        )
        assert cfg["LOGGING"]["loggers"]["apps"]["level"] == "WARNING"

    def test_hook_preserves_other_loggers_and_handlers(self):
        logging_cfg = {"loggers": {"apps": {"handlers": ["console"], "level": "INFO", "propagate": False}}}
        merged = apps_logger_follows_log_level({"LOGGING": logging_cfg, "LOG_LEVEL": "ERROR"})
        assert merged["LOGGING"]["loggers"]["apps"]["handlers"] == ["console"]
        assert merged["LOGGING"]["loggers"]["apps"]["propagate"] is False

    def test_hook_does_not_mutate_input(self):
        logging_cfg = {"loggers": {"apps": {"level": "INFO"}}}
        apps_logger_follows_log_level({"LOGGING": logging_cfg, "LOG_LEVEL": "ERROR"})
        assert logging_cfg["loggers"]["apps"]["level"] == "INFO"

    def test_wholesale_logging_override_wins(self):
        """A LOGGING replacement without 'loggers' is left alone entirely."""
        test_logging = {
            "version": 1,
            "handlers": {"null": {"class": "logging.NullHandler"}},
            "root": {"handlers": ["null"]},
        }
        assert apps_logger_follows_log_level({"LOGGING": test_logging, "LOG_LEVEL": "DEBUG"}) == {}
        assert "loggers" not in test_logging

    def test_hook_tolerates_missing_logging(self):
        assert apps_logger_follows_log_level({"LOG_LEVEL": "DEBUG"}) == {}

    def test_hook_skips_test_runs(self):
        """apps/settings/test.py LOGGING must win: no console logger injected in tests."""
        logging_cfg = {"loggers": {"apps": {"level": "INFO"}}}
        assert apps_logger_follows_log_level({"LOGGING": logging_cfg, "LOG_LEVEL": "DEBUG", "TESTING": True}) == {}

    def test_runtime_hook_is_noop_while_testing(self):
        """The live LOGGING of a test run must never be rewritten by the hook."""
        import copy

        from django.conf import settings

        snapshot = copy.deepcopy(settings.LOGGING)
        merged = apps_logger_follows_log_level({"LOGGING": settings.LOGGING, "LOG_LEVEL": "WARNING", "TESTING": True})
        assert merged == {}
        assert snapshot == settings.LOGGING
