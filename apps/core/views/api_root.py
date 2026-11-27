from ansible_base.lib.utils.views.ansible_base import AnsibleBaseView
from django.contrib.admindocs.views import simplify_regex
from django.urls import URLPattern, URLResolver, get_resolver
from rest_framework.permissions import AllowAny
from rest_framework.response import Response


class APIRootView(AnsibleBaseView):
    """
    Dynamically discovers and lists available API endpoints.

    Introspects the URL configuration to find all registered endpoints.
    Shows only direct children under the current path (not all descendants).
    Uses the same traversal order as Django's URL resolver, so the first
    matching pattern wins (like `show_urls --unsorted`).

    Usage:
        path('v1/', APIRootView.as_view(view_name='v1'), name='v1-root'),
        path('', APIRootView.as_view(view_name='my_project'), name='index'),
    """

    permission_classes = [AllowAny]
    view_name = None  # Set via as_view(view_name="...")

    def get_view_name(self):
        """Return the view name for breadcrumbs."""
        if self.view_name:
            return self.view_name
        # Fallback to default
        return "API Root"

    def get(self, request):
        resolver = get_resolver()

        # Derive prefix from request path (e.g., '/v1/' -> '/v1/')
        prefix = request.path if request.path.startswith("/") else "/" + request.path

        # Get the current view's URL name to exclude it from results
        current_url_name = getattr(request.resolver_match, "url_name", None)

        # ServicePrefixMiddleware supplies the external /api/<service> prefix.
        api_service_prefix = getattr(request, "_api_service_prefix", None)
        if api_service_prefix:
            child_prefix = api_service_prefix + prefix[len("/api") :]
        else:
            child_prefix = request.META.get("SCRIPT_NAME", "") + prefix

        endpoints = {}
        excluded_names = {current_url_name, "api-root"}
        for clean_path, pattern_name in self._extract_patterns(resolver.url_patterns, ""):
            if pattern_name in excluded_names:
                continue
            if pattern_name and pattern_name.endswith("-index"):
                continue
            child = self._direct_child(clean_path, prefix)
            if child is not None and child not in endpoints:
                endpoints[child] = request.build_absolute_uri(f"{child_prefix}{child}/")

        # Sort alphabetically for consistent output
        return Response(dict(sorted(endpoints.items())))

    @staticmethod
    def _direct_child(clean_path, prefix):
        """Return the first public, static segment under this prefix."""
        if not clean_path.startswith(prefix):
            return None
        relative_path = clean_path[len(prefix) :]
        if "__debug__" in relative_path or relative_path.startswith("_"):
            return None
        child = relative_path.strip("/").partition("/")[0]
        return child if child and "<" not in child else None

    def _extract_patterns(self, patterns, current_path):
        """
        Recursively extract URL patterns in traversal order.
        Yields (clean_path, pattern_name) tuples.
        """
        for pattern in patterns:
            raw_path = current_path + str(pattern.pattern)
            clean_path = simplify_regex(raw_path)

            if isinstance(pattern, URLResolver):
                # Yield the resolver path itself (for section detection)
                yield (clean_path, None)
                # Recurse into nested patterns
                yield from self._extract_patterns(pattern.url_patterns, raw_path)
            elif isinstance(pattern, URLPattern):
                # Yield leaf pattern with its name
                yield (clean_path, pattern.name)
