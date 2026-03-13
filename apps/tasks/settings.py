"""Settings specific for tasks application."""

DISPATCHERD_ENABLED = True
"""Background Task Configuration (Dispatcherd)
Dispatcherd is always enabled in this service (can be disabled in tests)
Override with METRICS_SERVICE_DISPATCHERD_ENABLED environment variable"""

# """Segment Write Key this needs to be set in environment variables to run locally in producitoon its mounted as a file"""
# SEGMENT_WRITE_KEY = "test-segment-write-key-change-in-production"
