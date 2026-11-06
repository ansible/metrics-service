"""Middleware that accepts or generates a request ID for every HTTP request."""

import uuid

from apps.core.request_context import (
    REQUEST_ID_HEADER,
    TRACEPARENT_HEADER,
    normalize_request_id,
    request_context,
    validate_traceparent,
)


class RequestIdMiddleware:
    """
    Put an ``X-Request-ID`` on the current context and echo it on the response.

    An inbound UUID is preserved; a missing or invalid header is replaced with
    a freshly generated UUID. The ID is also exposed as ``request.request_id``
    and set on the contextvar so downstream code (and the logging filter) can
    read it without access to the request object.

    A valid inbound W3C ``traceparent`` is bound alongside it so outbound calls
    made while handling the request can forward the same trace context.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request_id = normalize_request_id(request.headers.get(REQUEST_ID_HEADER)) or str(uuid.uuid4())
        traceparent = validate_traceparent(request.headers.get(TRACEPARENT_HEADER))
        request.request_id = request_id

        with request_context(request_id, traceparent, origin="http"):
            response = self.get_response(request)

        response[REQUEST_ID_HEADER] = request_id
        return response
