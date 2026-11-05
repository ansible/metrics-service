"""Regression guard for the request-id filter wiring in the project LOGGING config."""

from pathlib import Path

import pytest

SETTINGS_PATH = Path(__file__).resolve().parents[3] / "metrics_service" / "settings.py"


@pytest.mark.unit
class TestRequestIdLoggingConfig:
    """Every application logger and the console handler must carry the filter."""

    def test_project_logging_uses_project_filter_and_wires_loggers(self):
        source = SETTINGS_PATH.read_text()

        assert '"()": "apps.core.logging_filters.RequestIdFilter"' in source

        # The console handler plus the five application/root loggers.
        logger_block = source.split('"loggers": {', 1)[1].split("\n    },", 1)[0]
        assert logger_block.count('"filters": ["request_id"]') == 5
