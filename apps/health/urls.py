"""
URL configuration for health checks.
"""

from django.urls import path

from .views import HealthCheckView, LivenessProbeView, ReadinessProbeView

app_name = "health"

urlpatterns = [
    # Comprehensive health check
    path("", HealthCheckView.as_view(), name="health_check"),
    # Kubernetes probes
    path("liveness/", LivenessProbeView.as_view(), name="liveness"),
    path("readiness/", ReadinessProbeView.as_view(), name="readiness"),
]
