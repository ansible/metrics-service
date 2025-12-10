import re

from django.urls import get_resolver
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.reverse import reverse
from rest_framework.views import APIView


def _normalize_path(path):
    """
    Normalize URL pattern path by stripping regex anchors and format suffixes.

    DRF routers use regex patterns like '^organizations/$' or '^organizations\\.(?P<format>...)$'
    This normalizes them to simple paths like 'organizations/'.
    """
    # Strip regex anchors
    path = path.lstrip("^").rstrip("$")
    # Remove format suffix patterns like '\.(?P<format>[a-z0-9]+)/?'
    path = re.sub(r"\\\.\(\?P<format>[^)]+\)/?\$?", "/", path)
    # Clean up any remaining regex escapes
    path = path.replace("\\.", ".")
    return path


class APIRootView(APIView):
    """
    Dynamically discovers and lists available API endpoints.

    Introspects the URL configuration to find all registered endpoints.
    Shows only direct children under the current path (not all descendants).
    Prefix is automatically derived from request.path.

    Usage:
        path('v1/', APIRootView.as_view(), name='v1-root'),
        path('', APIRootView.as_view(), name='index'),
    """

    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        endpoints = {}
        resolver = get_resolver()

        # Derive prefix from request path (e.g., '/v1/' -> 'v1/')
        prefix = request.path.lstrip("/")

        # Get the current view's URL name to exclude it from results
        current_url_name = getattr(request.resolver_match, "url_name", None)

        self._extract_patterns(
            resolver.url_patterns, "", endpoints, request, prefix, current_url_name
        )

        # Sort alphabetically for consistent output
        return Response(dict(sorted(endpoints.items())))

    def _extract_patterns(
        self, patterns, current_path, endpoints, request, prefix, exclude_name=None, namespace=None
    ):
        """Recursively extract endpoints from URL patterns."""
        for pattern in patterns:
            # Get raw pattern string and normalize it
            raw_pattern = str(pattern.pattern)
            normalized_pattern = _normalize_path(raw_pattern)
            full_path = current_path + normalized_pattern

            # Handle nested includes (URLResolver)
            if hasattr(pattern, "url_patterns"):
                # Track namespace for nested patterns
                pattern_namespace = getattr(pattern, "namespace", None)
                child_namespace = f"{namespace}:{pattern_namespace}" if namespace and pattern_namespace else (pattern_namespace or namespace)

                # Check if this resolver is a direct child of our prefix
                if full_path.startswith(prefix):
                    relative_path = full_path[len(prefix) :]
                    if relative_path and relative_path != "/":
                        path_parts = relative_path.strip("/").split("/")
                        # Skip paths with parameters or debug patterns
                        if (
                            len(path_parts) == 1
                            and "<" not in relative_path
                            and "(?P<" not in raw_pattern
                            and "__debug__" not in relative_path
                        ):
                            # This is a direct child section (like v1/)
                            section_name = path_parts[0]
                            # Include SCRIPT_NAME for gateway prefix support
                            script_name = request.META.get("SCRIPT_NAME", "")
                            section_url = request.build_absolute_uri(script_name + "/" + full_path)
                            endpoints[section_name] = section_url

                # Always recurse to find named patterns (use raw path for recursion)
                self._extract_patterns(
                    pattern.url_patterns, current_path + normalized_pattern, endpoints, request, prefix, exclude_name, child_namespace
                )

            # Handle leaf patterns (URLPattern)
            elif hasattr(pattern, "name") and pattern.name:
                # Skip the current view itself
                if pattern.name == exclude_name:
                    continue

                # Must start with our prefix
                if not full_path.startswith(prefix):
                    continue

                # Get the path relative to our prefix
                relative_path = full_path[len(prefix) :]

                # Skip empty relative path (this is the index itself)
                if not relative_path or relative_path == "/":
                    continue

                # Skip if this is a nested path (has more slashes after prefix)
                # We only want direct children
                # e.g., for prefix='v1/', we want 'widgets/' but not 'widgets/<id>/'
                path_parts = relative_path.strip("/").split("/")
                if len(path_parts) > 1:
                    continue

                # Skip detail views (paths with parameters like <pk> or regex named groups)
                if "<" in relative_path or "(?P<" in raw_pattern:
                    continue

                # Skip format suffix patterns (like organizations.json)
                if "\\." in raw_pattern or ".(?P<format>" in raw_pattern:
                    continue

                # Skip index views (they're redundant with section links)
                # This includes -index and api-root (DRF router index)
                if pattern.name.endswith("-index") or pattern.name == "api-root":
                    continue

                # Build full URL name with namespace if applicable
                url_name = f"{namespace}:{pattern.name}" if namespace else pattern.name

                # Use a clean name for the endpoint (strip namespace prefix and suffixes)
                name = pattern.name.removesuffix("-list").removesuffix("-root")
                try:
                    endpoints[name] = reverse(url_name, request=request)
                except Exception:
                    # Skip if reverse fails (e.g., requires arguments)
                    pass
