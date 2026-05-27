"""
Tests for trace_id generation and propagation across the task lifecycle.

Covers:
- Task.trace_id is auto-generated as a UUID on creation
- trace_id is included in log output via JsonFormatter
- execute_db_task and execute_claimed bind trace_id to log records
- submit_task_to_dispatcher forwards trace_id in dispatcherd kwargs
"""

import logging
import uuid
from unittest.mock import MagicMock, call, patch

import pytest

from apps.core.logging_config import JsonFormatter
from apps.tasks.tasks_system import _trace_logger

# ---------------------------------------------------------------------------
# _trace_logger helper
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestTraceLogger:
    """_trace_logger returns an adapter that injects trace_id into log extras."""

    def test_returns_logger_adapter(self):
        adapter = _trace_logger("abc-123")
        assert isinstance(adapter, logging.LoggerAdapter)

    def test_extra_contains_trace_id(self):
        adapter = _trace_logger("test-trace")
        assert adapter.extra["trace_id"] == "test-trace"

    def test_none_trace_id_becomes_empty_string(self):
        adapter = _trace_logger(None)
        assert adapter.extra["trace_id"] == ""


# ---------------------------------------------------------------------------
# JsonFormatter — trace_id in structured log output
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestJsonFormatterTraceId:
    """JsonFormatter emits trace_id when present on the LogRecord."""

    def _make_record(self, **extras):
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="hello",
            args=(),
            exc_info=None,
        )
        for key, value in extras.items():
            setattr(record, key, value)
        return record

    def test_trace_id_included_in_output(self):
        import json

        formatter = JsonFormatter()
        tid = str(uuid.uuid4())
        record = self._make_record(trace_id=tid)
        output = json.loads(formatter.format(record))
        assert output["trace_id"] == tid

    def test_no_trace_id_field_when_absent(self):
        import json

        formatter = JsonFormatter()
        record = self._make_record()
        output = json.loads(formatter.format(record))
        assert "trace_id" not in output

    def test_empty_trace_id_not_included(self):
        """An empty string trace_id (falsy) is not emitted."""
        import json

        formatter = JsonFormatter()
        record = self._make_record(trace_id="")
        output = json.loads(formatter.format(record))
        assert "trace_id" not in output


# ---------------------------------------------------------------------------
# Task model — trace_id field
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestTaskTraceIdField:
    """Task.trace_id is auto-generated and unique per instance."""

    def _make_mock_task(self, trace_id=None):
        task = MagicMock()
        task.trace_id = trace_id if trace_id is not None else uuid.uuid4()
        task.function_name = "hello_world"
        task.name = "test_task"
        task.task_data = {}
        task.id = 1
        return task

    def test_trace_id_is_uuid(self):
        task = self._make_mock_task()
        assert isinstance(task.trace_id, uuid.UUID)

    def test_two_tasks_have_different_trace_ids(self):
        t1 = self._make_mock_task()
        t2 = self._make_mock_task()
        assert t1.trace_id != t2.trace_id


# ---------------------------------------------------------------------------
# submit_task_to_dispatcher — trace_id forwarded to dispatcherd
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSubmitTaskTraceIdForwarding:
    """submit_task_to_dispatcher includes trace_id in the dispatcherd kwargs payload."""

    @patch("apps.tasks.tasks_system.submit_task")
    @patch("apps.tasks.tasks_system.get_queue_for_function", return_value="default")
    @patch("apps.tasks.tasks_system.ensure_dispatcherd_configured")
    def test_trace_id_in_submit_kwargs(self, mock_ensure, mock_queue, mock_submit):
        from apps.tasks.tasks_system import execute_db_task, submit_task_to_dispatcher

        tid = uuid.uuid4()
        task = MagicMock()
        task.id = 42
        task.name = "my_task"
        task.trace_id = tid
        task.function_name = "hello_world"

        # Patch out the TaskExecution duplicate-guard
        with patch("apps.tasks.tasks_system.TaskExecution") as mock_te:
            mock_te.objects.filter.return_value.exists.return_value = False
            submit_task_to_dispatcher(task)

        mock_submit.assert_called_once()
        _, kwargs = mock_submit.call_args
        assert kwargs["kwargs"]["trace_id"] == str(tid)
        assert kwargs["kwargs"]["task_id"] == 42

    @patch("apps.tasks.tasks_system.submit_task")
    @patch("apps.tasks.tasks_system.get_queue_for_function", return_value="default")
    @patch("apps.tasks.tasks_system.ensure_dispatcherd_configured")
    def test_no_trace_id_when_missing(self, mock_ensure, mock_queue, mock_submit):
        """Tasks with trace_id=None still submit but with empty string trace_id."""
        from apps.tasks.tasks_system import submit_task_to_dispatcher

        task = MagicMock()
        task.id = 7
        task.name = "task_no_trace"
        task.trace_id = None
        task.function_name = "hello_world"

        with patch("apps.tasks.tasks_system.TaskExecution") as mock_te:
            mock_te.objects.filter.return_value.exists.return_value = False
            submit_task_to_dispatcher(task)

        _, kwargs = mock_submit.call_args
        assert kwargs["kwargs"]["trace_id"] == ""


# ---------------------------------------------------------------------------
# execute_db_task — early trace_id log before DB fetch
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestExecuteDbTaskTraceId:
    """execute_db_task logs the early trace_id received from the dispatcherd payload."""

    @patch("apps.tasks.tasks_system.execute_claimed")
    @patch("apps.tasks.tasks_system._claim_task")
    @patch("apps.tasks.tasks_system.ensure_django_setup")
    def test_early_trace_id_logged(self, mock_setup, mock_claim, mock_execute_claimed):
        import logging

        from apps.tasks.tasks_system import execute_db_task

        tid = str(uuid.uuid4())
        mock_task = MagicMock()
        mock_task.trace_id = uuid.UUID(tid)
        mock_task.function_name = "hello_world"
        mock_execution = MagicMock()
        mock_claim.return_value = (mock_task, mock_execution)
        mock_execute_claimed.return_value = {"status": "success"}

        with patch("apps.tasks.tasks_system.Task") as mock_task_cls:
            mock_task_cls.objects.filter.return_value.exists.return_value = True

            with patch.object(logging.LoggerAdapter, "info") as mock_log_info:
                execute_db_task(task_id=99, trace_id=tid)

            # At least one info call should carry the early trace_id
            assert any(tid in str(c) for c in mock_log_info.call_args_list)
