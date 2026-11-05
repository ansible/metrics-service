"""Unit tests for RequestIdMiddleware."""

import uuid

import pytest
from django.http import HttpResponse
from django.test import RequestFactory

from apps.core.middleware.request_id import RequestIdMiddleware
from apps.core.request_context import current_request_id


def _make_middleware():
    """Build a middleware with a get_response that records the active request ID."""
    captured = {}

    def get_response(request):
        captured["request_id"] = current_request_id()
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
