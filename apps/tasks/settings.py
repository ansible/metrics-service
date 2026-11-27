"""Settings specific for tasks application."""

import os

SEGMENT_TEST_MODE = False
"""Segment Test Mode
When True, appends '_Test' to all Segment event names to separate end-to-end
test data from real customer data. Override with METRICS_SERVICE_SEGMENT_TEST_MODE
environment variable."""

SEGMENT_URL = os.environ.get("MOCK_SEGMENT_URL", "")
"""Custom Segment API endpoint URL.
When set, Segment track calls are sent to this URL instead of the default
(https://api.segment.io). Useful for development and testing with a mock
Segment server. Override with METRICS_SERVICE_SEGMENT_URL or MOCK_SEGMENT_URL
environment variable."""
