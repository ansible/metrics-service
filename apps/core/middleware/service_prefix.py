"""
Service prefix middleware.

Allows the service to be accessed with a /<service-name> prefix:
- /api/<service-name>/v1/users → /api/v1/users
- /<service-name>/ping → /ping

For the /api/<service-name> case, Django resolves paths internally under
/api/..., while request-aware URL building replaces only the /api root with the
public prefix. For example, /api/v1/tasks/ becomes /api/metrics/v1/tasks/.

For the /<service-name> case, SCRIPT_NAME is set so reverse()
generates /<service-name>/... URLs.

The service name is determined by URL_PREFIX when set (e.g. URL_PREFIX="/api/metrics"
gives service_prefix="/metrics"), falling back to a name derived from ROOT_URLCONF.
"""

from django.conf import settings
from django.urls import set_script_prefix

from apps.core.url_prefix import replace_api_root


class ServicePrefixMiddleware:
    """
    Middleware that handles /<service-name> prefix in URLs.

    Two routing modes:
    1. /api/<service-name>/... → /api/... (no SCRIPT_NAME, canonical URLs)
    2. /<service-name>/... → /... (SCRIPT_NAME set for prefixed URLs)

    The prefix is taken from URL_PREFIX when set (e.g. "/api/metrics"), falling
    back to a name derived from ROOT_URLCONF (e.g. "metrics_service" → "/metrics-service").
    """

    def __init__(self, get_response):
        self.get_response = get_response
        url_prefix = getattr(settings, "URL_PREFIX", None)
        if url_prefix:
            # URL_PREFIX is the full API prefix, e.g. "/api/metrics"
            self.api_prefix = url_prefix.rstrip("/")
            # Derive the bare service prefix by stripping the leading "/api" segment
            self.service_prefix = self.api_prefix[4:] if self.api_prefix.startswith("/api/") else self.api_prefix
        else:
            # Fall back to deriving from ROOT_URLCONF (e.g. "metrics_service" → "/metrics-service")
            service_name = settings.ROOT_URLCONF.split(".")[0].replace("_", "-")
            self.service_prefix = f"/{service_name}"
            self.api_prefix = f"/api{self.service_prefix}"

    def __call__(self, request):
        path = request.path_info

        # Handle /api/<service-name>/... → /api/...
        # Resolve requests internally under /api/... and remember the public
        # root so request-aware URL generation can retain the /v1/... suffix.
        # Store original path for DRF breadcrumbs
        # Patch get_full_path to return the original path for templates
        api_prefix = self.api_prefix
        if path.startswith(api_prefix):
            request._original_path = path
            request._api_service_prefix = api_prefix
            new_path = "/api" + path[len(api_prefix) :] or "/api/"
            request.path_info = new_path
            request.path = new_path
            if hasattr(request, "environ"):
                request.environ["PATH_INFO"] = new_path

            # Patch get_full_path to return the original prefixed path
            # This ensures DRF templates show correct URLs for forms/links
            original_get_full_path = request.get_full_path

            def patched_get_full_path(force_append_slash=False):
                # Get the canonical path and replace /api/ with /api/<service>/
                canonical = original_get_full_path(force_append_slash)
                if canonical.startswith(("/api/", "/api?")):
                    return api_prefix + canonical[4:]
                return canonical

            request.get_full_path = patched_get_full_path

            # DRF's reverse() builds absolute links via request.build_absolute_uri().
            # Translate canonical /api/... URLs there so hyperlinked fields and
            # explicit DRF reverses use the externally reachable prefix.
            original_build_absolute_uri = request.build_absolute_uri

            def patched_build_absolute_uri(location=None):
                if location is not None:
                    location = replace_api_root(str(location), api_prefix)
                return original_build_absolute_uri(location)

            request.build_absolute_uri = patched_build_absolute_uri
        # Handle /<service-name>/... → /...
        # Set SCRIPT_NAME so reverse() generates /<service-name>/... URLs
        elif path.startswith(self.service_prefix):
            # Store original path for DRF breadcrumbs
            request._original_path = path
            new_path = path[len(self.service_prefix) :] or "/"
            request.path_info = new_path
            request.path = new_path
            request.META["SCRIPT_NAME"] = self.service_prefix
            set_script_prefix(self.service_prefix)
            if hasattr(request, "environ"):
                request.environ["SCRIPT_NAME"] = self.service_prefix
                request.environ["PATH_INFO"] = new_path

            # Patch get_full_path to return the original prefixed path
            # Django's get_full_path() doesn't include SCRIPT_NAME
            service_prefix = self.service_prefix
            original_get_full_path = request.get_full_path

            def patched_get_full_path(force_append_slash=False):
                return service_prefix + original_get_full_path(force_append_slash)

            request.get_full_path = patched_get_full_path

        return self.get_response(request)
