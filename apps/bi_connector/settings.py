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

# 30 requests/hour prevents runaway BI polling against the production AWX DB
REST_FRAMEWORK__DEFAULT_THROTTLE_CLASSES = ["dynaconf_merge_unique", "rest_framework.throttling.UserRateThrottle"]
REST_FRAMEWORK__DEFAULT_THROTTLE_RATES = {"dynaconf_merge": True, "user": "30/hour"}
