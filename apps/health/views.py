"""
Health check views for metrics_service.

This module provides health check endpoints for monitoring the service
status and dependencies, supporting both comprehensive health checks
and Kubernetes-style liveness/readiness probes.
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

    This view provides detailed health status information for the service
    and its dependencies. It supports selective health checks via query
    parameters and returns appropriate HTTP status codes.
    """

    def get(self, request):
        """
        Return comprehensive health status.

        This method executes health checks and returns a detailed status
        report including individual check results and overall service health.

        Args:
            request: HTTP request object, may contain 'check' query parameters
                    to specify which checks to run

        Returns:
            JsonResponse: Health status with appropriate HTTP status code
                - 200: All checks passed (healthy)
                - 503: One or more checks failed (unhealthy)
        """
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

    This view provides a basic liveness check that indicates whether
    the service is running and responsive. It's designed for Kubernetes
    liveness probes and should always return a successful response
    unless the service is completely down.
    """

    def get(self, request):
        """
        Return basic liveness status.

        This method returns a simple alive status without performing
        any complex checks. It's used by Kubernetes to determine if
        the service should be restarted.

        Args:
            request: HTTP request object

        Returns:
            JsonResponse: Simple alive status with 200 status code
        """
        return JsonResponse(
            {
                "status": "alive",
                "service": getattr(settings, "SERVICE_TYPE", "metrics-service"),
            }
        )


class ReadinessProbeView(View):
    """
    Readiness probe for Kubernetes - checks critical dependencies.

    This view checks critical service dependencies to determine if the
    service is ready to accept traffic. It's designed for Kubernetes
    readiness probes and will return failure if critical dependencies
    are unavailable.
    """

    def get(self, request):
        """
        Return readiness status based on critical checks.

        This method checks only critical dependencies that are required
        for the service to function properly. It's used by Kubernetes
        to determine if traffic should be routed to this instance.

        Args:
            request: HTTP request object

        Returns:
            JsonResponse: Readiness status with appropriate HTTP status code
                - 200: Service is ready to accept traffic
                - 503: Service is not ready (critical dependencies failed)
        """
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
