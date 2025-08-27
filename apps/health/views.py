"""
Health check views for metrics_service.
"""

import logging

from django.conf import settings
from django.http import JsonResponse
from django.views import View

from .checks import HEALTH_CHECKS

logger = logging.getLogger(__name__)


class HealthCheckView(View):
    """
    Comprehensive health check endpoint.
    """

    def get(self, request):
        """Return comprehensive health status."""
        checks = request.GET.getlist("check", HEALTH_CHECKS.keys())
        results = {}
        overall_status = "healthy"

        for check_name in checks:
            if check_name in HEALTH_CHECKS:
                try:
                    result = HEALTH_CHECKS[check_name]()
                    results[check_name] = result

                    # Update overall status if any check is unhealthy
                    if result.get("status") == "unhealthy":
                        overall_status = "unhealthy"

                except Exception as e:
                    logger.error(f"Health check {check_name} failed: {str(e)}")
                    results[check_name] = {
                        "status": "error",
                        "error": str(e),
                        "details": f"Health check {check_name} encountered an error",
                    }
                    overall_status = "unhealthy"
            else:
                results[check_name] = {
                    "status": "error",
                    "error": f"Unknown health check: {check_name}",
                    "details": f"Health check {check_name} not found",
                }
                overall_status = "unhealthy"

        response_data = {
            "status": overall_status,
            "service": getattr(settings, "SERVICE_TYPE", "metrics-service"),
            "version": "1.0.0",  # Update with actual version
            "checks": results,
            "available_checks": list(HEALTH_CHECKS.keys()),
        }

        # Return appropriate HTTP status code
        status_code = 200 if overall_status == "healthy" else 503

        return JsonResponse(response_data, status=status_code)


class LivenessProbeView(View):
    """
    Simple liveness probe for Kubernetes.
    """

    def get(self, request):
        """Return basic liveness status."""
        return JsonResponse(
            {
                "status": "alive",
                "service": getattr(settings, "SERVICE_TYPE", "metrics-service"),
            }
        )


class ReadinessProbeView(View):
    """
    Readiness probe for Kubernetes - checks critical dependencies.
    """

    def get(self, request):
        """Return readiness status based on critical checks."""
        # Only check critical dependencies for readiness
        critical_checks = ["database"]

        results = {}
        overall_status = "ready"

        for check_name in critical_checks:
            if check_name in HEALTH_CHECKS:
                try:
                    result = HEALTH_CHECKS[check_name]()
                    results[check_name] = result

                    if result.get("status") != "healthy":
                        overall_status = "not_ready"

                except Exception as e:
                    logger.error(f"Readiness check {check_name} failed: {str(e)}")
                    results[check_name] = {"status": "error", "error": str(e)}
                    overall_status = "not_ready"

        response_data = {
            "status": overall_status,
            "service": getattr(settings, "SERVICE_TYPE", "metrics-service"),
            "critical_checks": results,
        }

        # Return appropriate HTTP status code
        status_code = 200 if overall_status == "ready" else 503

        return JsonResponse(response_data, status=status_code)
