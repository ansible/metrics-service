"""Unit coverage for SQL Server-specific database connection behavior."""

from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest

from apps.tasks import utils
from apps.tasks.cron_scheduler import UnifiedTaskScheduler


class _RawPyodbcConnection:
    __module__ = "pyodbc"

    def __init__(self, fetchone=(1,)):
        self.cursor_obj = MagicMock()
        self.cursor_obj.fetchone.return_value = fetchone

    @contextmanager
    def cursor(self):
        yield self.cursor_obj


def test_get_db_connection_probes_raw_pyodbc_with_cursor():
    raw_connection = _RawPyodbcConnection()
    django_connection = MagicMock(connection=raw_connection)

    with patch("django.db.connections", {"awx": django_connection}):
        result = utils.get_db_connection("awx")

    assert result is raw_connection
    raw_connection.cursor_obj.execute.assert_called_once_with("SELECT 1")
    django_connection.close.assert_not_called()


def test_check_db_ready_uses_sql_server_metadata_syntax():
    raw_connection = _RawPyodbcConnection(fetchone=(1,))

    assert utils._check_db_ready(raw_connection, ("main_unifiedjob",)) is True

    query, params = raw_connection.cursor_obj.execute.call_args.args
    assert "SELECT CASE WHEN EXISTS" in query
    assert "INFORMATION_SCHEMA.TABLES" in query
    assert "?" in query
    assert params == ["main_unifiedjob"]


@pytest.mark.parametrize("lock_result", [0, 1])
def test_run_with_lock_uses_and_releases_sql_server_application_lock(lock_result):
    connection = MagicMock(vendor="microsoft")
    cursor = MagicMock()
    cursor.fetchone.return_value = (lock_result,)
    connection.cursor.return_value.__enter__.return_value = cursor
    connection.cursor.return_value.__exit__.return_value = False
    callback = MagicMock(return_value={"status": "success"})

    with patch("django.db.connection", connection), patch("django.db.close_old_connections"):
        result = utils.run_with_lock("hourly_summary", "hourly_summary", callback, value=3)

    assert result == {"status": "success"}
    callback.assert_called_once_with(value=3)
    acquire_sql, acquire_params = cursor.execute.call_args_list[0].args
    release_sql, release_params = cursor.execute.call_args_list[1].args
    assert "sp_getapplock" in acquire_sql
    assert "@LockOwner = 'Session'" in acquire_sql
    assert acquire_params == ["hourly_summary"]
    assert "sp_releaseapplock" in release_sql
    assert release_params == ["hourly_summary"]


def test_run_with_lock_skips_callback_when_sql_server_lock_is_held():
    connection = MagicMock(vendor="microsoft")
    cursor = MagicMock()
    cursor.fetchone.return_value = (-1,)
    connection.cursor.return_value.__enter__.return_value = cursor
    connection.cursor.return_value.__exit__.return_value = False
    callback = MagicMock()

    with patch("django.db.connection", connection), patch("django.db.close_old_connections"):
        result = utils.run_with_lock("hourly_summary", "hourly_summary", callback)

    callback.assert_not_called()
    assert result["status"] == "error"
    assert "Could not acquire lock" in result["error"]
    assert cursor.execute.call_count == 1


def test_run_with_lock_releases_sql_server_lock_when_callback_raises():
    connection = MagicMock(vendor="microsoft")
    cursor = MagicMock()
    cursor.fetchone.return_value = (0,)
    connection.cursor.return_value.__enter__.return_value = cursor
    connection.cursor.return_value.__exit__.return_value = False
    callback = MagicMock(side_effect=RuntimeError("task failed"))

    with (
        patch("django.db.connection", connection),
        patch("django.db.close_old_connections"),
        pytest.raises(RuntimeError, match="task failed"),
    ):
        utils.run_with_lock("hourly_summary", "hourly_summary", callback)

    assert "sp_releaseapplock" in cursor.execute.call_args_list[-1].args[0]


def test_scheduler_does_not_run_postgres_lock_cleanup_on_sql_server():
    scheduler = UnifiedTaskScheduler()
    connection = MagicMock(vendor="microsoft")

    with patch("django.db.connection", connection):
        scheduler._cleanup_stale_advisory_locks()

    connection.cursor.assert_not_called()
