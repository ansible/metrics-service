"""dispatcherd worker class that owns the runtime log level refresh thread.

dispatcherd creates its worker pool with ``multiprocessing``'s ``fork`` context
from the ``run_dispatcherd`` process. Anything running at that moment is
duplicated into every child: a forked child inherits the parent's open file
descriptors, so a parent thread that is between ``connect()`` and the end of a
query can leave the child sharing a half-open socket. That is the class of bug
``connections.close_all()`` in :mod:`apps.tasks.management.commands.run_dispatcherd`
fixes, and it is why the log level refresh thread must not exist pre-fork.

``TaskWorker.on_start`` is dispatcherd's documented integration hook and is
called by ``dispatcherd.worker.target.work_loop_internal`` as the first thing
each worker child does, i.e. strictly after the fork. Starting the thread here
gives every worker its own poller (AAP-79584) and keeps the dispatcherd parent
thread-free, so the parent never touches the database at fork time.
"""

from __future__ import annotations

import logging

from dispatcherd.worker.task import TaskWorker

logger = logging.getLogger(__name__)


class LogLevelSyncWorker(TaskWorker):
    """A :class:`TaskWorker` that reconciles the runtime log level while idle.

    The managed loggers are inherited from the parent at fork time, so a worker
    starts with whatever level the parent had. Task entry (:func:`execute_db_task`)
    already refreshes the level for the task itself; this thread covers the
    periods between tasks so a ``--clear`` or a TTL expiry is reflected in
    worker logs without waiting for the next task.

    Configured through ``worker_cls`` in ``apps/settings/dispatcherd.yaml``.
    """

    def on_start(self) -> None:
        """Start the refresh thread in the worker child (post-fork)."""
        super().on_start()
        try:
            from apps.core.logging_control import start_refresh_thread

            start_refresh_thread()
        except Exception as exc:  # noqa: BLE001 - log control must not kill the worker
            logger.debug("Runtime log level refresh thread not started: %s", exc)

    def on_shutdown(self) -> None:
        """Stop the refresh thread before the worker exits."""
        try:
            from apps.core.logging_control import stop_refresh_thread

            stop_refresh_thread()
        except Exception as exc:  # noqa: BLE001 - shutdown must not raise
            logger.debug("Runtime log level refresh thread not stopped cleanly: %s", exc)
        super().on_shutdown()
