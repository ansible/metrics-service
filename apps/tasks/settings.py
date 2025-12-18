"""Settings specific for tasks application."""

DISPATCHERD_ENABLED = True
"""Background Task Configuration (Dispatcherd)
Dispatcherd is always enabled in this service (can be disabled in tests)
Override with METRICS_SERVICE_DISPATCHERD_ENABLED environment variable"""


SEGMENT_WRITE_KEY = "test-segment-write-key-change-in-production"
"""Segment Write Key"""
