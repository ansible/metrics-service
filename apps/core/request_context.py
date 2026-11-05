"""
Request ID context propagation helpers.

A single source of truth for "the current request ID", importable from the web
process, the scheduler, dispatcherd workers and management commands.

The ID is kept in a :class:`contextvars.ContextVar` so that it follows async
work and resets automatically at the end of each context. Validation is
UUID-only: an arbitrary string read from a header, DB row or task payload must
never be able to reach the log output unmodified.
"""

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
origin_var: ContextVar[str | None] = ContextVar("origin", default=None)


def current_request_id() -> str | None:
    """Return the request ID of the current context, or None if unset."""
    return request_id_var.get()


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


@contextmanager
def request_context(request_id: object, *, origin: str | None = None) -> Iterator[None]:
    """
    Set the current request ID for the duration of the block.

    The context variable is reset in ``finally`` so nested use (for example a
    worker executing a task that creates a follow-on task) is safe and cannot
    leak the ID into unrelated work.
    """
    request_token = request_id_var.set(normalize_request_id(request_id))
    origin_token = origin_var.set(origin)
    try:
        yield
    finally:
        origin_var.reset(origin_token)
        request_id_var.reset(request_token)
