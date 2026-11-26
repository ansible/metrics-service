from django.urls import get_resolver

from apps.core.views import APIRootView

_cached_prefixes: set[str] | None = None


def _get_known_prefixes() -> set[str]:
    """Build and cache the set of all registered URL path prefixes."""
    global _cached_prefixes
    if _cached_prefixes is not None:
        return _cached_prefixes

    resolver = get_resolver()
    prefixes: set[str] = set()

    def collect(patterns, current_path=""):
        for pattern in patterns:
            full_path = current_path + str(pattern.pattern)
            prefixes.add(full_path)
            if hasattr(pattern, "url_patterns"):
                collect(pattern.url_patterns, full_path)

    collect(resolver.url_patterns)
    _cached_prefixes = prefixes
    return prefixes


class APIRootViewMiddleware:
    """
    Middleware that serves an endpoint index for any path ending in '/'
    that would otherwise 404 but has child routes registered.

    This allows automatic index pages at any level of the URL hierarchy
    without explicitly registering them.

    Example:
        - /v2/ would show an index if there are routes under /v2/*
        - /some/deep/path/ would show an index if children exist
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        # Only intercept 404s for paths ending with /
        is_404_with_trailing_slash = response.status_code == 404 and request.path.endswith("/")
        if is_404_with_trailing_slash and self._has_child_routes(request.path):
            # Serve the endpoint index view
            view = APIRootView.as_view()
            index_response = view(request)
            # Render the response if needed (DRF responses need rendering)
            if hasattr(index_response, "render"):
                index_response.render()
            return index_response

        return response

    def _has_child_routes(self, path):
        """Check if there are any routes under the given path (uses cached prefix set)."""
        prefix = path.lstrip("/")
        known = _get_known_prefixes()
        return any(p.startswith(prefix) and p != prefix for p in known)
