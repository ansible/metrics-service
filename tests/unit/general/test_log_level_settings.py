"""Unit tests that all configured loggers honor METRICS_SERVICE_LOG_LEVEL (ES-SUP-2).

Django settings cannot be reliably reloaded in tests (dynaconf caches and the
development settings overlay logger levels with DEBUG), so these tests extract
the LOGGING / LOG_LEVEL expressions from metrics_service/settings.py and
evaluate them directly against different LOG_LEVEL values. This verifies the
production wiring: no logger is hard-coded above the configured level.
"""

import ast
import os
from pathlib import Path
from unittest import mock

import pytest

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

    @pytest.mark.parametrize("level", ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"])
    def test_all_loggers_follow_log_level(self, level):
        """Every configured logger resolves to LOG_LEVEL; none is hard-coded."""
        logging_config = _evaluate_logging(level)
        for name in LOGGERS:
            assert logging_config["loggers"][name]["level"] == level, (
                f"logger {name!r} does not honor METRICS_SERVICE_LOG_LEVEL"
            )

    def test_apps_logger_not_hardcoded(self):
        """Regression guard: the 'apps' logger must not be hard-coded to INFO."""
        assert _evaluate_logging("WARNING")["loggers"]["apps"]["level"] == "WARNING"
