"""
Mixins for BI connector views.
"""

from rest_framework.exceptions import ImproperlyConfigured, NotFound
from rest_framework.throttling import UserRateThrottle


class BiConnectorThrottle(UserRateThrottle):
    """
    Per-user throttle scoped to BI connector endpoints only.

    Rate is controlled by REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]["bi_connector"],
    defaulting to 30/hour. Override without restart:
        METRICS_SERVICE_REST_FRAMEWORK__DEFAULT_THROTTLE_RATES__BI_CONNECTOR=60/hour
    """

    scope = "bi_connector"

    def get_rate(self):
        try:
            return super().get_rate()
        except ImproperlyConfigured:
            return "30/hour"


class BiConnectorEnabledMixin:
    """
    Returns 404 for all requests when the BI_CONNECTOR feature flag is disabled.

    The endpoint appears to not exist when the feature is off — this avoids
    revealing the API surface to unauthenticated users or misconfigured tools.
    Enable via: METRICS_SERVICE_FEATURE_ENABLED__BI_CONNECTOR=true
    or toggle the FEATURE_BI_CONNECTOR_ENABLED AAPFlag at runtime.

    Also applies BiConnectorThrottle (30 req/hour per user) to all BI endpoints.
    This throttle is scoped exclusively to BI connector views and does not affect
    any other API endpoints.
    """

    throttle_classes = [BiConnectorThrottle]

    def initial(self, request, *args, **kwargs):
        from apps.tasks.task_groups import get_feature_enabled_from_db

        if not get_feature_enabled_from_db("BI_CONNECTOR", default=False):
            raise NotFound()
        super().initial(request, *args, **kwargs)
