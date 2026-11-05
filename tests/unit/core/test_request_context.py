"""Unit tests for the request ID context helpers."""

import uuid

import pytest

from apps.core.request_context import (
    current_request_id,
    normalize_request_id,
    origin_var,
    request_context,
)


@pytest.mark.unit
class TestNormalizeRequestId:
    """normalize_request_id only accepts UUIDs."""

    def test_accepts_uuid_string(self):
        value = str(uuid.uuid4())
        assert normalize_request_id(value) == value

    def test_accepts_uuid_object(self):
        value = uuid.uuid4()
        assert normalize_request_id(value) == str(value)

    def test_canonicalises_case_and_braces(self):
        value = uuid.uuid4()
        assert normalize_request_id(str(value).upper()) == str(value)
        assert normalize_request_id("{" + str(value) + "}") == str(value)

    @pytest.mark.parametrize("value", [None, "", "abc", "not-a-uuid", "'; DROP TABLE tasks_task; --", 123, object()])
    def test_rejects_non_uuid(self, value):
        assert normalize_request_id(value) is None


@pytest.mark.unit
class TestRequestContext:
    """request_context manages the contextvar safely."""

    def test_current_request_id_is_none_outside_context(self):
        assert current_request_id() is None

    def test_context_sets_and_resets(self):
        value = str(uuid.uuid4())
        with request_context(value, origin="test"):
            assert current_request_id() == value
            assert origin_var.get() == "test"
        assert current_request_id() is None
        assert origin_var.get() is None

    def test_context_normalises_value(self):
        value = uuid.uuid4()
        with request_context(value):
            assert current_request_id() == str(value)

    def test_context_discards_invalid_value(self):
        with request_context("not-a-uuid"):
            assert current_request_id() is None

    def test_context_nests_and_restores(self):
        outer = str(uuid.uuid4())
        inner = str(uuid.uuid4())
        with request_context(outer):
            with request_context(inner):
                assert current_request_id() == inner
            assert current_request_id() == outer
        assert current_request_id() is None

    def test_context_resets_on_exception(self):
        value = str(uuid.uuid4())
        with pytest.raises(RuntimeError), request_context(value):
            raise RuntimeError("boom")
        assert current_request_id() is None
