"""
Request ID and trace context propagation helpers.

A single source of truth for "the current request context" — the request ID, the
inbound W3C ``traceparent`` and the entry point that opened the context —
importable from the web process, the scheduler, dispatcherd workers and
management commands.

Both values live in :class:`contextvars.ContextVar` instances so they follow
async work and reset automatically at the end of each context. Request IDs are
validated as UUIDs and trace contexts against the W3C ``traceparent`` format: an
arbitrary string read from a header, a DB row or a task payload must never reach
a log line or an outbound header unmodified.

See ``docs/trace-propagation.md`` for the header contract.
"""

import logging
import re
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

logger = logging.getLogger(__name__)

REQUEST_ID_HEADER = "X-Request-ID"
TRACEPARENT_HEADER = "traceparent"

# W3C Trace Context: version-traceid-spanid-flags, lower-case hex. Versions above
# 00 may append version-specific fields, and a receiver must ignore fields it does
# not understand; only version ff is invalid (W3C Trace Context §3.2.2).
_TRACEPARENT_RE = re.compile(r"^([0-9a-f]{2})-([0-9a-f]{32})-([0-9a-f]{16})-([0-9a-f]{2})(-.*)?$")

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
"""The originating request ID. The ONLY ``request_id`` contextvar in the project."""

traceparent_var: ContextVar[str | None] = ContextVar("traceparent", default=None)
origin_var: ContextVar[str | None] = ContextVar("origin", default=None)


def normalize_request_id(value: object) -> str | None:
    """
    Validate value as a UUID and return its canonical string form.

    Accepts a :class:`uuid.UUID` or a string. Returns ``None`` for anything
    that is not a valid UUID (including ``None``, empty strings and arbitrary
    text) so invalid values are discarded rather than logged.
    """
    if value is None:
        return None
    if isinstance(value, uuid.UUID):
        return str(value)
    if not isinstance(value, str):
        return None
    try:
        return str(uuid.UUID(value))
    except (AttributeError, TypeError, ValueError):
        return None


def validate_traceparent(value: object) -> str | None:
    """
    Validate a W3C ``traceparent`` header value and return it normalised.

    The value is stripped and lower-cased, then checked field by field. Versions
    other than ``00`` are accepted: W3C Trace Context requires a receiver to
    accept any version other than ``ff`` and to ignore trailing fields it does
    not understand, so rejecting them would silently drop traces sent by future
    OpenTelemetry SDKs. Invalid values are dropped rather than repaired.
    """
    if not isinstance(value, str) or not value.strip():
        if value:
            logger.debug("dropping non-string or empty traceparent: %r", value)
        return None

    normalised = value.strip().lower()
    match = _TRACEPARENT_RE.match(normalised)
    if match is None:
        logger.debug("dropping malformed traceparent: %r", value)
        return None

    version, trace_id, span_id = match.group(1), match.group(2), match.group(3)
    if version == "ff":
        logger.debug("dropping traceparent with forbidden version ff: %r", value)
        return None
    if int(trace_id, 16) == 0 or int(span_id, 16) == 0:
        logger.debug("dropping traceparent with all-zero trace or span id: %r", value)
        return None
    return normalised


def current_request_id() -> str | None:
    """Return the request ID of the current context, or None if unset."""
    return request_id_var.get()


def current_traceparent() -> str | None:
    """Return the inbound ``traceparent`` of the current context, or None if unset."""
    return traceparent_var.get()


def outbound_headers(request_id: str | None = None) -> dict[str, str]:
    """
    Build the propagation headers for an outbound HTTP call.

    Uses *request_id* when one is supplied (and valid), otherwise the ID of the
    current context. The W3C ``traceparent`` is forwarded only when the inbound
    request actually carried a valid one: this service does not mint spans, so
    synthesising a value would corrupt real traces.

    Returns an empty dict when there is no usable context, so callers outside a
    request or a restored worker context degrade silently to today's behaviour.
    """
    rid = normalize_request_id(request_id) if request_id is not None else current_request_id()
    if not rid:
        logger.debug("no request context; outbound headers omitted")
        return {}

    headers = {REQUEST_ID_HEADER: rid}
    if traceparent := current_traceparent():
        headers[TRACEPARENT_HEADER] = traceparent
    return headers


@contextmanager
def request_context(
    request_id: object = None,
    traceparent: str | None = None,
    *,
    origin: str | None = None,
) -> Iterator[None]:
    """
    Set the current request context for the duration of the block.

    ``request_id`` is validated as a UUID and ``traceparent`` against the W3C
    format; invalid values bind as ``None`` instead of being propagated.
    ``origin`` records which entry point opened the context (``http``,
    ``worker``, ...). All variables are reset in ``finally`` so nested use (for
    example a worker executing a task that creates a follow-on task) is safe and
    cannot leak the context into unrelated work.
    """
    request_token = request_id_var.set(normalize_request_id(request_id))
    traceparent_token = traceparent_var.set(validate_traceparent(traceparent))
    origin_token = origin_var.set(origin)
    try:
        yield
    finally:
        origin_var.reset(origin_token)
        traceparent_var.reset(traceparent_token)
        request_id_var.reset(request_token)
