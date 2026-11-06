"""Unit tests for the request ID / trace context helpers."""

import re
import uuid
from pathlib import Path

import pytest

from apps.core.request_context import (
    REQUEST_ID_HEADER,
    TRACEPARENT_HEADER,
    current_request_id,
    current_traceparent,
    normalize_request_id,
    origin_var,
    outbound_headers,
    request_context,
    request_id_var,
    validate_traceparent,
)

VALID_TRACEPARENT = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"

MIDDLEWARE_DIR = Path(__file__).resolve().parents[3] / "apps" / "core" / "middleware"


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
class TestValidateTraceparent:
    """validate_traceparent implements the W3C header contract."""

    def test_accepts_valid_version_00(self):
        assert validate_traceparent(VALID_TRACEPARENT) == VALID_TRACEPARENT

    def test_normalises_case_and_whitespace(self):
        assert validate_traceparent(f"  {VALID_TRACEPARENT.upper()}  ") == VALID_TRACEPARENT

    def test_accepts_future_versions_and_trailing_fields(self):
        """W3C requires accepting any version except ff, ignoring extra fields."""
        future = "01-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
        assert validate_traceparent(future) == future
        assert validate_traceparent(f"{future}-extra-field") == f"{future}-extra-field"

    @pytest.mark.parametrize(
        "value",
        [
            None,
            "",
            "   ",
            b"00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01",
            "garbage",
            "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7",  # missing flags
            "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-zz",  # bad flags
            "00-00000000000000000000000000000000-00f067aa0ba902b7-01",  # zero trace id
            "00-4bf92f3577b34da6a3ce929d0e0e4736-0000000000000000-01",  # zero span id
            "ff-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01",  # forbidden version
        ],
    )
    def test_rejects_invalid_values(self, value):
        assert validate_traceparent(value) is None


@pytest.mark.unit
class TestRequestContext:
    """request_context manages the contextvars safely."""

    def test_current_request_id_is_none_outside_context(self):
        assert current_request_id() is None
        assert current_traceparent() is None

    def test_context_sets_and_resets(self):
        value = str(uuid.uuid4())
        with request_context(value, VALID_TRACEPARENT, origin="test"):
            assert current_request_id() == value
            assert current_traceparent() == VALID_TRACEPARENT
            assert origin_var.get() == "test"
        assert current_request_id() is None
        assert current_traceparent() is None
        assert origin_var.get() is None

    def test_request_id_is_optional(self):
        with request_context():
            assert current_request_id() is None

    def test_context_normalises_value(self):
        value = uuid.uuid4()
        with request_context(value):
            assert current_request_id() == str(value)

    def test_context_discards_invalid_value(self):
        with request_context("not-a-uuid", "also-not-a-traceparent"):
            assert current_request_id() is None
            assert current_traceparent() is None

    def test_context_nests_and_restores(self):
        outer = str(uuid.uuid4())
        inner = str(uuid.uuid4())
        with request_context(outer, VALID_TRACEPARENT):
            with request_context(inner):
                assert current_request_id() == inner
                assert current_traceparent() is None
            assert current_request_id() == outer
            assert current_traceparent() == VALID_TRACEPARENT
        assert current_request_id() is None

    def test_context_resets_on_exception(self):
        value = str(uuid.uuid4())
        with pytest.raises(RuntimeError), request_context(value, VALID_TRACEPARENT):
            raise RuntimeError("boom")
        assert current_request_id() is None
        assert current_traceparent() is None


@pytest.mark.unit
class TestOutboundHeaders:
    """outbound_headers is the only way propagation headers are produced."""

    def test_empty_without_context(self):
        assert outbound_headers() == {}

    def test_includes_request_id_from_context(self):
        request_id = str(uuid.uuid4())
        with request_context(request_id):
            assert outbound_headers() == {REQUEST_ID_HEADER: request_id}

    def test_accepts_explicit_request_id(self):
        request_id = str(uuid.uuid4())
        assert outbound_headers(request_id) == {REQUEST_ID_HEADER: request_id}

    def test_explicit_invalid_request_id_returns_nothing_even_inside_context(self):
        with request_context(str(uuid.uuid4())):
            assert outbound_headers("not-a-uuid") == {}

    def test_canonicalises_request_id(self):
        request_id = uuid.uuid4()
        assert outbound_headers(str(request_id).upper()) == {REQUEST_ID_HEADER: str(request_id)}

    def test_omits_traceparent_when_inbound_had_none(self):
        with request_context(str(uuid.uuid4())):
            assert TRACEPARENT_HEADER not in outbound_headers()

    def test_forwards_valid_traceparent(self):
        request_id = str(uuid.uuid4())
        with request_context(request_id, VALID_TRACEPARENT):
            assert outbound_headers() == {REQUEST_ID_HEADER: request_id, TRACEPARENT_HEADER: VALID_TRACEPARENT}

    @pytest.mark.parametrize(
        "traceparent",
        [
            "",
            "garbage",
            "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7",  # missing flags
            "00-00000000000000000000000000000000-00f067aa0ba902b7-01",  # zero trace id
            "00-4bf92f3577b34da6a3ce929d0e0e4736-0000000000000000-01",  # zero span id
            "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-zz",  # bad flags
            "ff-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01",  # forbidden version
        ],
    )
    def test_invalid_traceparent_never_reaches_outbound_headers(self, traceparent):
        """A rejected trace context is dropped, but the request ID still propagates."""
        request_id = str(uuid.uuid4())
        with request_context(request_id, traceparent):
            assert current_traceparent() is None
            assert outbound_headers() == {REQUEST_ID_HEADER: request_id}

    def test_future_version_traceparent_reaches_outbound_headers(self):
        """W3C requires accepting versions other than ff, so 01-... must survive."""
        future = "01-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
        request_id = str(uuid.uuid4())
        with request_context(request_id, future):
            assert outbound_headers()[TRACEPARENT_HEADER] == future


@pytest.mark.unit
class TestSingleRequestIdContextVar:
    """
    Exactly one ``ContextVar("request_id")`` may be live.

    Two modules holding their own contextvar would silently split the context.
    """

    def test_no_middleware_module_defines_its_own_request_id_contextvar(self):
        pattern = re.compile(r"ContextVar\(\s*[\"']request_id[\"']")
        offenders = sorted(
            path.name for path in MIDDLEWARE_DIR.glob("*.py") if pattern.search(path.read_text(encoding="utf-8"))
        )

        assert offenders == []

    def test_shared_var_is_the_exported_one(self):
        from apps.core import request_context as module

        assert module.request_id_var is request_id_var
