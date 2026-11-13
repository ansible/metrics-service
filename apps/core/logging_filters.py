"""Project-owned logging filters."""

from ansible_base.lib.logging.filters.request_id import RequestIdFilter as DABRequestIdFilter

from apps.core.request_context import current_request_id


class RequestIdFilter(DABRequestIdFilter):
    """
    Add ``request_id`` to every log record.

    Keeps DAB's existing header/thread-local behaviour and then prefers the
    current contextvar, which is what lets scheduler and dispatcherd worker
    processes — where no Django request exists — tag their log records.
    """

    def filter(self, record):
        super().filter(record)
        record.request_id = current_request_id() or record.request_id
        return True
