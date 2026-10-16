"""Best-effort database telemetry for customer-facing Analytics API requests."""

import logging

from django.conf import settings
from django.urls import Resolver404, resolve
from django.utils import timezone

logger = logging.getLogger(__name__)


_ANALYTICS_VIEW_OPERATIONS = {
    "analytics:v1:root": "discovery",
    "analytics:v1:rows": "rows",
    "analytics:v1:collect": "collect",
}


def _operation_for_request(request):
    """Resolve the fixed Analytics API operation, including preflight requests."""
    match = getattr(request, "resolver_match", None)
    view_name = getattr(match, "view_name", None)
    if view_name is None:
        path = request.path_info
        url_prefix = getattr(settings, "URL_PREFIX", None)
        if url_prefix:
            api_prefix = url_prefix.rstrip("/")
            service_prefix = api_prefix[4:] if api_prefix.startswith("/api/") else api_prefix
            if path == api_prefix or path.startswith(f"{api_prefix}/"):
                path = "/api" + path[len(api_prefix) :]
            elif path == service_prefix or path.startswith(f"{service_prefix}/"):
                path = path[len(service_prefix) :] or "/"
        else:
            service_name = settings.ROOT_URLCONF.split(".")[0].replace("_", "-")
            service_prefix = f"/{service_name}"
            if path == service_prefix or path.startswith(f"{service_prefix}/"):
                path = path[len(service_prefix) :] or "/"
        try:
            view_name = resolve(path).view_name
        except Resolver404:
            return None
    return _ANALYTICS_VIEW_OPERATIONS.get(view_name)


def record_analytics_api_request(request, status_code: int) -> None:
    """Persist one route/status counter without affecting API responses."""
    try:
        operation = _operation_for_request(request)
        if operation is None:
            return

        from apps.analytics.models import AnalyticsAPIUsageCounter

        AnalyticsAPIUsageCounter.record_request(
            usage_date=timezone.now().date(),
            operation=operation,
            status_class=status_code // 100,
        )
    except Exception:
        # Telemetry must not change the response returned to the API caller.
        logger.exception("Failed to record Analytics API usage counter")


class AnalyticsAPIUsageMiddleware:
    """Count requests handled by the Analytics API without recording request data."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        record_analytics_api_request(request, response.status_code)
        return response
