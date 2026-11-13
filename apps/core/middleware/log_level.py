"""Middleware that applies the runtime log level override before each request."""

import logging

from apps.core.logging_control import sync_from_db

logger = logging.getLogger(__name__)


class LogLevelMiddleware:
    """Apply the shared runtime log level on each request.

    Runs before the view so a request made after ``set-log-level`` is logged at
    the new level. The sync is throttled inside ``sync_from_db`` (one database
    lookup per ``RUNTIME_LOG_LEVEL_REFRESH_SECONDS`` per process) and never
    raises: log-level control must not break request handling.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            sync_from_db()
        except Exception as exc:  # noqa: BLE001 - never fail a request over log control
            logger.debug("Runtime log level middleware skipped: %s", exc)
        return self.get_response(request)
