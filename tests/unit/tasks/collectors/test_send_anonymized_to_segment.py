"""
Unit tests for apps/tasks/collectors/send_anonymized_to_segment.py

Tests cover:
- SEGMENT_TEST_MODE=True appends '_Test' suffix to the Segment event name
- SEGMENT_TEST_MODE=False (default) leaves the event name unchanged
- Helper functions: _get_payloads_to_send, _handle_successful_send,
  _handle_failed_send, and the main send_anonymized_to_segment task
"""

from unittest.mock import MagicMock, patch

import pytest

from apps.tasks.collectors.send_anonymized_to_segment import (
    _handle_failed_send,
    _handle_successful_send,
    _process_single_payload,
    send_anonymized_to_segment,
)

# ---------------------------------------------------------------------------
# SEGMENT_TEST_MODE behaviour
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSegmentTestMode:
    """Tests for the SEGMENT_TEST_MODE event-name suffix feature."""

    def _make_payload(self, event_name: str = "Controller Metrics Daily Rollup") -> MagicMock:
        """Return a minimal mock AnonymizedMetricsPayload."""
        payload = MagicMock()
        payload.id = 1
        payload.status = "pending"
        payload.retry_count = 0
        payload.segment_user_id = "test-user-id"
        payload.segment_event_name = event_name
        payload.anonymized_data = {"test": "data"}
        payload.daily_summary = None
        payload.can_retry.return_value = True
        return payload

    @patch("apps.tasks.collectors.send_anonymized_to_segment.send_to_segment")
    def test_test_mode_enabled_appends_test_suffix(self, mock_send_to_segment, settings):
        """When SEGMENT_TEST_MODE=True, '_Test' is appended to the event name."""
        settings.SEGMENT_TEST_MODE = True
        mock_send_to_segment.return_value = "success"

        payload = self._make_payload("Controller Metrics Daily Rollup")
        results = {"sent": 0, "failed": 0, "skipped": 0, "recovered": 0}

        _process_single_payload(payload, results)

        mock_send_to_segment.assert_called_once()
        _, call_kwargs = mock_send_to_segment.call_args
        assert call_kwargs["event_name"] == "Controller Metrics Daily Rollup_Test"
        assert results["sent"] == 1

    @patch("apps.tasks.collectors.send_anonymized_to_segment.send_to_segment")
    def test_test_mode_disabled_keeps_original_event_name(self, mock_send_to_segment, settings):
        """When SEGMENT_TEST_MODE=False, the event name is sent unchanged."""
        settings.SEGMENT_TEST_MODE = False
        mock_send_to_segment.return_value = "success"

        payload = self._make_payload("Controller Metrics Daily Rollup")
        results = {"sent": 0, "failed": 0, "skipped": 0, "recovered": 0}

        _process_single_payload(payload, results)

        mock_send_to_segment.assert_called_once()
        _, call_kwargs = mock_send_to_segment.call_args
        assert call_kwargs["event_name"] == "Controller Metrics Daily Rollup"
        assert results["sent"] == 1

    @patch("apps.tasks.collectors.send_anonymized_to_segment.send_to_segment")
    def test_test_mode_absent_keeps_original_event_name(self, mock_send_to_segment, settings):
        """When SEGMENT_TEST_MODE is not set at all, the event name is unchanged."""
        # Remove the attribute if it exists so getattr falls back to the default
        if hasattr(settings, "SEGMENT_TEST_MODE"):
            delattr(settings, "SEGMENT_TEST_MODE")
        mock_send_to_segment.return_value = "success"

        payload = self._make_payload("My Event")
        results = {"sent": 0, "failed": 0, "skipped": 0, "recovered": 0}

        _process_single_payload(payload, results)

        _, call_kwargs = mock_send_to_segment.call_args
        assert call_kwargs["event_name"] == "My Event"


# ---------------------------------------------------------------------------
# _handle_successful_send
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestHandleSuccessfulSend:
    """Tests for _handle_successful_send helper."""

    def test_marks_payload_sent_and_increments_counter(self):
        payload = MagicMock()
        payload.daily_summary = None
        results = {"sent": 0, "failed": 0, "skipped": 0, "recovered": 0}

        _handle_successful_send(payload, results)

        assert payload.status == "sent"
        payload.save.assert_called_once()
        assert results["sent"] == 1

    def test_updates_daily_summary_status(self):
        payload = MagicMock()
        payload.daily_summary = MagicMock()
        results = {"sent": 0, "failed": 0, "skipped": 0, "recovered": 0}

        _handle_successful_send(payload, results)

        assert payload.daily_summary.status == "sent"
        payload.daily_summary.save.assert_called_once()

    def test_summary_save_failure_does_not_raise(self):
        """A failure updating the daily summary must not propagate."""
        payload = MagicMock()
        payload.daily_summary = MagicMock()
        payload.daily_summary.save.side_effect = Exception("DB error")
        results = {"sent": 0, "failed": 0, "skipped": 0, "recovered": 0}

        _handle_successful_send(payload, results)

        assert results["sent"] == 1


# ---------------------------------------------------------------------------
# _handle_failed_send
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestHandleFailedSend:
    """Tests for _handle_failed_send helper."""

    def test_sets_retry_status_and_increments_retry_count(self):
        payload = MagicMock()
        payload.retry_count = 2
        results = {"sent": 0, "failed": 0, "skipped": 0, "recovered": 0}

        _handle_failed_send(payload, "timeout", results)

        assert payload.status == "retry"
        assert payload.retry_count == 3
        assert "timeout" in payload.error_message
        payload.save.assert_called_once()
        assert results["failed"] == 1


# ---------------------------------------------------------------------------
# send_anonymized_to_segment (top-level task)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSendAnonymizedToSegmentTask:
    """Tests for the send_anonymized_to_segment task function."""

    @patch("apps.tasks.collectors.send_anonymized_to_segment._get_payloads_to_send")
    def test_returns_success_with_empty_payload_list(self, mock_get_payloads):
        """No payloads → success result with all-zero counters."""
        mock_get_payloads.return_value = []

        result = send_anonymized_to_segment()

        assert result["status"] == "success"
        assert result["results"] == {"sent": 0, "failed": 0, "skipped": 0, "recovered": 0}
        assert result["total_processed"] == 0

    @patch("apps.tasks.collectors.send_anonymized_to_segment._get_payloads_to_send")
    def test_returns_error_on_unexpected_exception(self, mock_get_payloads):
        """An unexpected exception must return an error result, not raise."""
        mock_get_payloads.side_effect = RuntimeError("boom")

        result = send_anonymized_to_segment()

        assert result["status"] == "error"
        assert "boom" in result["error"]

    @patch("apps.tasks.collectors.send_anonymized_to_segment.send_to_segment")
    @patch("apps.tasks.collectors.send_anonymized_to_segment._get_payloads_to_send")
    def test_processes_each_payload(self, mock_get_payloads, mock_send_to_segment, settings):
        """All payloads in the list are processed and sent."""
        settings.SEGMENT_TEST_MODE = False
        mock_send_to_segment.return_value = "success"

        def make_payload(pid: int) -> MagicMock:
            p = MagicMock()
            p.id = pid
            p.status = "pending"
            p.retry_count = 0
            p.segment_user_id = f"user-{pid}"
            p.segment_event_name = "My Event"
            p.anonymized_data = {}
            p.daily_summary = None
            p.can_retry.return_value = True
            return p

        mock_get_payloads.return_value = [make_payload(1), make_payload(2)]

        result = send_anonymized_to_segment()

        assert result["status"] == "success"
        assert result["results"]["sent"] == 2
        assert result["total_processed"] == 2
