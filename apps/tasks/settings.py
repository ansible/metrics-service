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

# BI Connector: long-lived token auth for Tableau/Power BI connectors
INSTALLED_APPS = ["dynaconf_merge_unique", "rest_framework.authtoken"]

REST_FRAMEWORK__DEFAULT_AUTHENTICATION_CLASSES = [
    "dynaconf_merge_unique",
    "rest_framework.authentication.TokenAuthentication",
]

# Throttle AWX DB queries — 30 requests/hour prevents runaway BI polling against the production DB
REST_FRAMEWORK__DEFAULT_THROTTLE_CLASSES = ["dynaconf_merge_unique", "rest_framework.throttling.UserRateThrottle"]
REST_FRAMEWORK__DEFAULT_THROTTLE_RATES = {"dynaconf_merge": True, "user": "30/hour"}
