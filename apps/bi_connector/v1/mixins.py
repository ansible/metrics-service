"""
Mixins for BI connector views.
"""

from django.core.exceptions import ImproperlyConfigured
from rest_framework.authentication import SessionAuthentication, TokenAuthentication
from rest_framework.exceptions import NotFound
from rest_framework.throttling import UserRateThrottle


def is_bi_collector_enabled(collector_name: str, default: bool = True) -> bool:
    """
    Check if a specific billing collector is enabled via the BI_CONNECTOR_COLLECTORS setting.

    Falls back to METRICS_SERVICE_BI_CONNECTOR_COLLECTORS__<name> env override,
    then to `default`. The BI_CONNECTOR feature flag is a separate gate — this
    only checks the per-collector granularity within an already-enabled BI connector.
    """
    import json

    try:
        from apps.dynamic_settings.models import Setting

        setting = Setting.objects.filter(setting_key="BI_CONNECTOR_COLLECTORS").first()
        if setting and setting.current_value:
            try:
                collectors = json.loads(setting.current_value)
                if isinstance(collectors, dict) and collector_name in collectors:
                    return bool(collectors[collector_name])
            except json.JSONDecodeError:
                pass
        from django.conf import settings as django_settings

        override = getattr(django_settings, "BI_CONNECTOR_COLLECTORS", {})
        if isinstance(override, dict) and collector_name in override:
            return bool(override[collector_name])
        return default
    except Exception:
        return default


class BiConnectorThrottle(UserRateThrottle):
    """
    Per-user throttle scoped to BI connector endpoints only.

    Rate is controlled by REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]["bi_connector"],
    defaulting to 30/hour. Override without restart:
        METRICS_SERVICE_REST_FRAMEWORK__DEFAULT_THROTTLE_RATES__BI_CONNECTOR=60/hour
    """

    scope = "bi_connector"

    def get_rate(self):
        """Return configured rate, falling back to 30/hour if not set."""
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

    authentication_classes is set here (not globally in settings.py) so that
    TokenAuthentication is scoped only to BI views — it does not affect any other
    service endpoint.
    """

    authentication_classes = [TokenAuthentication, SessionAuthentication]
    throttle_classes = [BiConnectorThrottle]

    def initial(self, request, *args, **kwargs):
        """Raise NotFound if BI_CONNECTOR flag is disabled; otherwise delegate to DRF."""
        from apps.tasks.task_groups import get_feature_enabled_from_db

        if not get_feature_enabled_from_db("BI_CONNECTOR", default=False):
            raise NotFound()
        super().initial(request, *args, **kwargs)


class DashboardCollectionMixin(BiConnectorEnabledMixin):
    """
    Extends BiConnectorEnabledMixin with a second flag check for dashboard endpoints.

    Returns 404 when either the BI_CONNECTOR flag or the DASHBOARD_COLLECTION flag
    is disabled. Both must be enabled for Layer 3 (dashboard) endpoints to respond.

    Check order: BI_CONNECTOR first (via super()), then DASHBOARD_COLLECTION.
    This matches the parent's documented behaviour and ensures operators see a
    consistent 404 when BI_CONNECTOR is off, regardless of the dashboard flag.

    Enable dashboard collection via: METRICS_SERVICE_FEATURE_ENABLED__DASHBOARD_COLLECTION=true
    """

    def initial(self, request, *args, **kwargs):
        """Check BI_CONNECTOR then DASHBOARD_COLLECTION; raise NotFound if either is disabled."""
        from apps.tasks.task_groups import get_feature_enabled_from_db

        super().initial(request, *args, **kwargs)  # checks BI_CONNECTOR, auth, throttle
        if not get_feature_enabled_from_db("DASHBOARD_COLLECTION", default=False):
            raise NotFound()
