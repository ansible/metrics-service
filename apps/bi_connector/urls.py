"""
Top-level URL configuration for the BI connector app.

Mounts all layers under their respective prefixes. The main metrics_service/urls.py
auto-discovers this module via LOADED_APPS — no changes needed there.

Layer 1 (pre-aggregated metrics):  /api/v1/metrics/
Layer 2 (live AWX DB):             /api/v1/controller/
Layer 3 (dashboard collected data):/api/v1/dashboard/
"""

from django.urls import include, path

app_name = "bi_connector"

urlpatterns = [
    path("api/v1/metrics/", include("apps.bi_connector.v1.metrics_urls", namespace="metrics")),
    path("api/v1/controller/", include("apps.bi_connector.v1.controller_urls", namespace="controller")),
    path("api/v1/dashboard/", include("apps.bi_connector.v1.dashboard_urls", namespace="dashboard")),
]
