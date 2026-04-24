"""
Mixins for BI connector views.
"""

from rest_framework.exceptions import NotFound


class BiConnectorEnabledMixin:
    """
    Returns 404 for all requests when the BI_CONNECTOR feature flag is disabled.

    The endpoint appears to not exist when the feature is off — this avoids
    revealing the API surface to unauthenticated users or misconfigured tools.
    Enable via: METRICS_SERVICE_FEATURE_ENABLED__BI_CONNECTOR=true
    or toggle the FEATURE_BI_CONNECTOR_ENABLED AAPFlag at runtime.
    """

    def initial(self, request, *args, **kwargs):
        from apps.tasks.task_groups import get_feature_enabled_from_db

        if not get_feature_enabled_from_db("BI_CONNECTOR", default=False):
            raise NotFound()
        super().initial(request, *args, **kwargs)
