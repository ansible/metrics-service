"""
Tests for request-context propagation into the Segment send path.

``send_to_segment`` passes ``headers=outbound_headers()`` to metrics-utility's
``StorageSegment``. Whether that mapping reaches the wire depends on the
installed metrics-utility release, so these tests drive the real
``StorageSegment`` and assert on the headers of the actual ``requests.post``
call — the only assertion that cannot pass for the wrong reason.

Upstream support is blocked on ansible/metrics-utility#635, which is not in any
published release yet (``uv.lock`` pins a version whose ``_send_batch``
hard-codes its headers). The test that asserts headers *are* sent is therefore
strict-xfail: it fails today *by design*, and it will fail loudly as XPASS once
the dependency is bumped, forcing the marker to be removed rather than letting
the feature stay silently untraced. The no-context case asserts headers are
*not* sent; it is a plain test that must keep passing.
"""

import uuid
from unittest.mock import patch

import pytest

from apps.core.request_context import REQUEST_ID_HEADER, TRACEPARENT_HEADER, request_context
from apps.tasks.collectors.send_anonymized_to_segment import send_to_segment

BLOCKED_REASON = "blocked on ansible/metrics-utility#635 release (StorageSegment drops caller headers)"

VALID_TRACEPARENT = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"


class _FakeResponse:
    """Minimal stand-in for a ``requests.Response``."""

    status_code = 200
    text = "ok"

    def raise_for_status(self):
        return None


@pytest.fixture
def segment_post():
    """Run ``send_to_segment`` against the real StorageSegment, capturing the POST."""
    with patch("metrics_utility.library.storage.segment.requests.post", return_value=_FakeResponse()) as post:
        yield post


def _send(settings) -> dict:
    settings.SEGMENT_WRITE_KEY = "test-key"
    result = send_to_segment(
        user_id="test-user",
        event_name="test_event",
        segment_data={"host_count": 1},
    )
    assert result["status"] == "success", result
    return result


@pytest.mark.unit
@pytest.mark.xfail(strict=True, reason=BLOCKED_REASON)
def test_segment_post_carries_request_id_header(settings, segment_post):
    request_id = str(uuid.uuid4())

    with request_context(request_id, VALID_TRACEPARENT):
        _send(settings)

    assert segment_post.call_count == 1
    headers = segment_post.call_args.kwargs["headers"]
    assert headers[REQUEST_ID_HEADER] == request_id
    assert headers[TRACEPARENT_HEADER] == VALID_TRACEPARENT
    # The library's own headers must survive the merge.
    assert headers["Content-Type"] == "application/json"


@pytest.mark.unit
def test_segment_post_omits_propagation_headers_without_context(settings, segment_post):
    """
    Outside a request context no propagation header is sent — not even an empty one.

    Unlike the test above this passes today, because *adding* headers is what the
    upstream release unlocks; omitting them must keep working afterwards.
    """
    _send(settings)

    assert segment_post.call_count == 1
    headers = segment_post.call_args.kwargs["headers"]
    assert REQUEST_ID_HEADER not in headers
    assert TRACEPARENT_HEADER not in headers
    assert headers["Content-Type"] == "application/json"
