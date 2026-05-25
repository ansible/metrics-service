"""
BI Connector app settings.

Adds token authentication app and per-user rate limiting for BI tool service accounts.
Token auth is scoped to BI views via BiConnectorEnabledMixin.authentication_classes,
NOT merged into the global DRF default — only /api/v1/bi/ endpoints accept tokens.
"""

# rest_framework.authtoken is required for drf_create_token and TokenAuthentication,
# but we deliberately do NOT merge TokenAuthentication into DEFAULT_AUTHENTICATION_CLASSES
# here — that would expose token auth on every service endpoint.  See mixins.py.
INSTALLED_APPS = ["dynaconf_merge_unique", "rest_framework.authtoken"]

# Maximum date window (in days) for BI connector AWX queries.
# Override via environment variable: METRICS_SERVICE_BI_CONNECTOR_MAX_DAYS_DEFAULT=14
BI_CONNECTOR_MAX_DAYS_DEFAULT = 7
# Tighter limit for events queries — main_jobevent is one of the largest AWX tables.
# Override via: METRICS_SERVICE_BI_CONNECTOR_MAX_DAYS_EVENTS=5
BI_CONNECTOR_MAX_DAYS_EVENTS = 3
