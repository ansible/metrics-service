"""
Unit tests for apps/tasks/api_utils.py.
"""

import pytest


@pytest.mark.unit
def test_build_error_response_basic():
    from apps.tasks.api_utils import build_error_response

    result = build_error_response("Something failed")
    assert result["error"] == "Something failed"
    assert result["status_code"] == 400
    assert "timestamp" in result
    assert "details" not in result


@pytest.mark.unit
def test_build_error_response_custom_status_code():
    from apps.tasks.api_utils import build_error_response

    result = build_error_response("Not found", status_code=404)
    assert result["status_code"] == 404


@pytest.mark.unit
def test_build_error_response_with_details():
    from apps.tasks.api_utils import build_error_response

    result = build_error_response("Bad input", details={"field": "name", "reason": "required"})
    assert "details" in result
    assert result["details"]["field"] == "name"


@pytest.mark.unit
def test_build_error_response_no_details_when_none():
    from apps.tasks.api_utils import build_error_response

    result = build_error_response("oops", details=None)
    assert "details" not in result


@pytest.mark.unit
def test_build_error_response_timestamp_is_string():
    from apps.tasks.api_utils import build_error_response

    result = build_error_response("x")
    assert isinstance(result["timestamp"], str)
    assert "T" in result["timestamp"]
