"""
Unit tests for apps/tasks/services/output_formatter.py.
"""

from unittest.mock import MagicMock

import pytest


@pytest.fixture
def formatter():
    from apps.tasks.services.output_formatter import OutputFormatter

    stdout = MagicMock()
    style = MagicMock()
    style.SUCCESS.side_effect = lambda msg: f"SUCCESS:{msg}"
    style.ERROR.side_effect = lambda msg: f"ERROR:{msg}"
    style.WARNING.side_effect = lambda msg: f"WARNING:{msg}"
    return OutputFormatter(stdout=stdout, style=style), stdout, style


@pytest.mark.unit
def test_output_formatter_success(formatter):
    fmt, stdout, style = formatter
    fmt.success("done")
    style.SUCCESS.assert_called_once_with("done")
    stdout.write.assert_called_once_with("SUCCESS:done")


@pytest.mark.unit
def test_output_formatter_error(formatter):
    fmt, stdout, style = formatter
    fmt.error("fail")
    style.ERROR.assert_called_once_with("fail")
    stdout.write.assert_called_once_with("ERROR:fail")


@pytest.mark.unit
def test_output_formatter_warning(formatter):
    fmt, stdout, style = formatter
    fmt.warning("careful")
    style.WARNING.assert_called_once_with("careful")
    stdout.write.assert_called_once_with("WARNING:careful")


@pytest.mark.unit
def test_output_formatter_info(formatter):
    fmt, stdout, style = formatter
    fmt.info("informational")
    stdout.write.assert_called_once_with("informational")
    style.SUCCESS.assert_not_called()


@pytest.mark.unit
def test_output_formatter_write(formatter):
    fmt, stdout, style = formatter
    fmt.write("plain text")
    stdout.write.assert_called_once_with("plain text")


@pytest.mark.unit
def test_output_formatter_write_separator_default(formatter):
    fmt, stdout, style = formatter
    fmt.write_separator()
    stdout.write.assert_called_once_with("=" * 50)


@pytest.mark.unit
def test_output_formatter_write_separator_custom(formatter):
    fmt, stdout, style = formatter
    fmt.write_separator(char="-", length=20)
    stdout.write.assert_called_once_with("-" * 20)
