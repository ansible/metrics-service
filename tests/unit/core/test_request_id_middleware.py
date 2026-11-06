"""Unit tests for RequestIdMiddleware."""

import uuid

import pytest
from django.http import HttpResponse
from django.test import RequestFactory

from apps.core.middleware.request_id import RequestIdMiddleware
from apps.core.request_context import current_request_id, current_traceparent, origin_var

VALID_TRACEPARENT = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"


def _make_middleware():
    """Build a middleware with a get_response that records the active context."""
    captured = {}

    def get_response(request):
        captured["request_id"] = current_request_id()
        captured["traceparent"] = current_traceparent()
        captured["origin"] = origin_var.get()
        captured["request_attr"] = getattr(request, "request_id", None)
        return HttpResponse("ok")

    return RequestIdMiddleware(get_response), captured


@pytest.mark.unit
class TestRequestIdMiddleware:
    """The middleware accepts, generates and echoes X-Request-ID."""

    def test_preserves_inbound_uuid(self):
        value = str(uuid.uuid4())
        request = RequestFactory().get("/", HTTP_X_REQUEST_ID=value)
        middleware, captured = _make_middleware()

        response = middleware(request)

        assert request.request_id == value
        assert captured["request_id"] == value
        assert captured["request_attr"] == value
        assert response["X-Request-ID"] == value

    def test_generates_uuid_when_header_missing(self):
        request = RequestFactory().get("/")
        middleware, captured = _make_middleware()

        response = middleware(request)

        generated = response["X-Request-ID"]
        assert uuid.UUID(generated)
        assert request.request_id == generated
        assert captured["request_id"] == generated

    def test_replaces_invalid_header(self):
        request = RequestFactory().get("/", HTTP_X_REQUEST_ID="not-a-uuid")
        middleware, captured = _make_middleware()

        response = middleware(request)

        assert response["X-Request-ID"] != "not-a-uuid"
        assert uuid.UUID(response["X-Request-ID"])
        assert captured["request_id"] == response["X-Request-ID"]

    def test_context_is_reset_after_response(self):
        middleware, _ = _make_middleware()
        middleware(RequestFactory().get("/", HTTP_X_REQUEST_ID=str(uuid.uuid4())))

        assert current_request_id() is None
        assert current_traceparent() is None
        assert origin_var.get() is None

    def test_records_http_origin(self):
        middleware, captured = _make_middleware()

        middleware(RequestFactory().get("/"))

        assert captured["origin"] == "http"

    def test_binds_valid_traceparent(self):
        middleware, captured = _make_middleware()
        request = RequestFactory().get("/", HTTP_TRACEPARENT=VALID_TRACEPARENT)

        middleware(request)

        assert captured["traceparent"] == VALID_TRACEPARENT
        assert current_traceparent() is None

    def test_drops_malformed_traceparent(self):
        middleware, captured = _make_middleware()
        request = RequestFactory().get("/", HTTP_TRACEPARENT="not-a-traceparent")

        response = middleware(request)

        assert captured["traceparent"] is None
        assert uuid.UUID(response["X-Request-ID"])
