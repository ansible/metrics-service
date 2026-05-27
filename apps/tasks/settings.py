"""Settings specific for tasks application."""

DISPATCHERD_ENABLED = True
"""Background Task Configuration (Dispatcherd)
Dispatcherd is always enabled in this service (can be disabled in tests)
Override with METRICS_SERVICE_DISPATCHERD_ENABLED environment variable"""

SEGMENT_TEST_MODE = False
"""Segment Test Mode
When True, appends '_Test' to all Segment event names to separate end-to-end
test data from real customer data. Override with METRICS_SERVICE_SEGMENT_TEST_MODE
environment variable."""

# SEGMENT_WRITE_KEY = "test-segment-write-key-change-in-production"
# """Segment Write Key this needs to be set in environment variables to run locally in producitoon its mounted as a file"""

IDEMPOTENCY_WINDOW_SECONDS = 600
"""Idempotency window for task retry requests (seconds).
When a caller supplies an Idempotency-Key header on POST /api/v1/tasks/{id}/retry/,
a duplicate request carrying the same key within this window returns the original
response without creating a new execution record. Defaults to 10 minutes (600 s).
Override with METRICS_SERVICE_IDEMPOTENCY_WINDOW_SECONDS environment variable."""
