"""
URL configuration for the apps package.

This file is for custom URL patterns that need to load BEFORE individual app
URLs. Use this for:

- Service-level customizations (top-level urls.py is framework-managed)
- Priority/override patterns that must match before app-defined routes
- Cross-app endpoints combining functionality from multiple apps

This file loads at step 3 in the URL loading order, before individual apps
(step 4). For full documentation, see: metrics_service/urls.py

## Example

    from django.urls import path
    from apps.core.views import SomeView

    urlpatterns = [
        path("api/v1/priority-endpoint/", SomeView.as_view(), name="priority"),
    ]

"""

from django.urls import path

from apps.core.views.metrics import PrometheusMetricsView
from apps.core.views.redirects import ServicePrefixRedirectView

urlpatterns = [
    # Prometheus metrics endpoint — requires system admin or auditor.
    # Registered at both paths so clients that append a trailing slash get the
    # same response without an extra redirect (the gateway round-trip breaks
    # Django's APPEND_SLASH 301, causing a 404 for the slash form).
    path("api/v1/metrics", PrometheusMetricsView.as_view(), name="prometheus-django-metrics"),
    path("api/v1/metrics/", PrometheusMetricsView.as_view()),
    # Redirect to the canonical states list. URL_PREFIX replaces only /api,
    # retaining /v1/... (e.g. /api/v1/... → /api/metrics/v1/...). With no
    # URL_PREFIX, this remains under the local /api/v1/ path.
    path(
        "api/v1/feature_flags/",
        ServicePrefixRedirectView.as_view(url="/api/v1/feature_flags/states/", permanent=True),
    ),
]
