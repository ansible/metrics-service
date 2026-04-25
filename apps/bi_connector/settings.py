"""
BI Connector app settings.

Adds token authentication and per-user rate limiting for BI tool service accounts.
These settings merge into the global REST_FRAMEWORK config via Dynaconf.
"""

# Long-lived token auth for Tableau/Power BI/Grafana service accounts
INSTALLED_APPS = ["dynaconf_merge_unique", "rest_framework.authtoken"]

REST_FRAMEWORK__DEFAULT_AUTHENTICATION_CLASSES = [
    "dynaconf_merge_unique",
    "rest_framework.authentication.TokenAuthentication",
]

# Rate limit scoped to "bi_connector" — only applies when BiConnectorThrottle is used.
# Applied per-view via BiConnectorEnabledMixin.throttle_classes, not globally.
# Override with: METRICS_SERVICE_REST_FRAMEWORK__DEFAULT_THROTTLE_RATES__BI_CONNECTOR=60/hour
REST_FRAMEWORK__DEFAULT_THROTTLE_RATES = {"dynaconf_merge": True, "bi_connector": "30/hour"}

# Maximum date window (in days) for BI connector AWX queries.
# Override via environment variable: METRICS_SERVICE_BI_CONNECTOR_MAX_DAYS_DEFAULT=14
BI_CONNECTOR_MAX_DAYS_DEFAULT = 7
# Tighter limit for events queries — main_jobevent is one of the largest AWX tables.
# Override via: METRICS_SERVICE_BI_CONNECTOR_MAX_DAYS_EVENTS=5
BI_CONNECTOR_MAX_DAYS_EVENTS = 3
