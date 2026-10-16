"""Best-effort database telemetry for metrics-service API requests."""

import logging

from django.conf import settings
from django.urls import Resolver404, resolve
from django.utils import timezone

logger = logging.getLogger(__name__)


_EXCLUDED_API_ROUTE_PREFIXES = ("api/v1/metrics", "api/v1/docs")
# Keep this PR scoped to BYO-BI analytics routes; add other API namespaces here to expand coverage.
_TRACKED_API_VIEW_NAME_PREFIXES = ("analytics:",)


def _endpoint_for_request(request):
    """Return a stable endpoint label for an API route, excluding infrastructure endpoints."""
    match = getattr(request, "resolver_match", None)
    if match is None:
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
            match = resolve(path)
        except Resolver404:
            return None

    route = str(getattr(match, "route", "")).lstrip("^").rstrip("$").strip("/")
    if (route != "api" and not route.startswith("api/")) or any(
        route == prefix or route.startswith(f"{prefix}/") for prefix in _EXCLUDED_API_ROUTE_PREFIXES
    ):
        return None

    endpoint_name = getattr(match, "view_name", None)
    if endpoint_name and endpoint_name.startswith(_TRACKED_API_VIEW_NAME_PREFIXES):
        return endpoint_name
    return None


def record_api_usage(request, status_code: int) -> None:
    """Persist one API endpoint/status counter without affecting the response."""
    try:
        endpoint_name = _endpoint_for_request(request)
        if endpoint_name is None:
            return

        from apps.analytics.models import APIUsageCounter

        APIUsageCounter.record_request(
            usage_date=timezone.now().date(),
            endpoint_name=endpoint_name,
            status_class=status_code // 100,
        )
    except Exception:
        # Telemetry must not change the response returned to the API caller.
        logger.exception("Failed to record API usage counter")


class APIUsageMiddleware:
    """Count requests handled by metrics-service API endpoints without recording request data."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        record_api_usage(request, response.status_code)
        return response
