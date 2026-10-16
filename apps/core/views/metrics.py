import os

from ansible_base.lib.utils.views.ansible_base import AnsibleBaseView
from ansible_base.rbac.api.permissions import IsSystemAdminOrAuditor
from django.http import HttpResponse
from django_prometheus.exports import ExportToDjangoView
from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, generate_latest, multiprocess
from prometheus_client.gc_collector import GCCollector
from prometheus_client.platform_collector import PlatformCollector
from prometheus_client.process_collector import ProcessCollector
from rest_framework.settings import api_settings

from apps.core.authentication import MetricsServiceTokenAuthentication


class IsSystemAdminOrAuditorOrServiceToken(IsSystemAdminOrAuditor):
    """Allow the validated internal service token in addition to normal metrics-view RBAC."""

    def has_permission(self, request, view):
        # Only this view enables the service-token authentication class; it has already verified
        # the signature, expiry, and local service issuer before setting request.auth.
        if getattr(view, "allow_service_token", False) and request.auth == "MetricsServiceTokenAuthentication":
            return True
        return super().has_permission(request, view)


def _multiprocess_registry() -> CollectorRegistry:
    """Combine worker metrics while retaining the default Python process collectors."""
    registry = CollectorRegistry()
    multiprocess.MultiProcessCollector(registry)
    GCCollector(registry)
    PlatformCollector(registry)
    ProcessCollector(registry=registry)
    return registry


class PrometheusMetricsView(AnsibleBaseView):
    """Prometheus endpoint for system admins, auditors, and this service's internal scraper."""

    authentication_classes = [*api_settings.DEFAULT_AUTHENTICATION_CLASSES, MetricsServiceTokenAuthentication]
    permission_classes = [IsSystemAdminOrAuditorOrServiceToken]
    allow_service_token = True

    def get(self, request):
        if "PROMETHEUS_MULTIPROC_DIR" in os.environ:
            return HttpResponse(
                generate_latest(_multiprocess_registry()),
                content_type=CONTENT_TYPE_LATEST,
            )
        return ExportToDjangoView(request)
