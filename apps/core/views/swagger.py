"""
Custom Swagger UI view with service-prefix-aware schema URL.

When the metrics service sits behind a gateway (e.g. the AAP Gateway) that
proxies requests under a prefix such as ``/api/metrics``, Django's ``reverse()``
generates paths that omit that prefix (e.g. ``/api/v1/docs/schema/``).  The
``ServicePrefixMiddleware`` stores the stripped prefix on the request as
``_api_service_prefix`` so that views can reconstruct the full external URL.

``MetricsSpectacularSwaggerView`` overrides ``_get_schema_url`` to replace only
the internal ``/api`` root with the public API root. The remaining ``/v1/...``
path is preserved, producing ``/api/metrics/v1/docs/schema/``.
"""

from django.conf import settings
from drf_spectacular.plumbing import get_relative_url, set_query_parameters
from drf_spectacular.views import SpectacularSwaggerView
from rest_framework.reverse import reverse

from apps.core.url_prefix import replace_api_root


class MetricsSpectacularSwaggerView(SpectacularSwaggerView):
    """Swagger UI view that maps the internal schema path to the public API root.

    Without this override, the Swagger UI fetches the OpenAPI schema from the
    bare Django-generated path (e.g. ``/api/v1/docs/schema/``).  When the
    service is accessed through a gateway that prefixes all requests with
    ``/api/metrics``, that bare path is unreachable via the gateway and the
    Swagger UI fails to load.

    The override replaces the internal ``/api`` segment with the prefix stored
    by ``ServicePrefixMiddleware`` on ``request._api_service_prefix`` (or the
    configured ``URL_PREFIX``), retaining ``/v1/docs/schema/``. For example,
    ``/api/v1/docs/schema/`` becomes ``/api/metrics/v1/docs/schema/``.

    When the service is accessed directly (no gateway, no prefix), the
    attribute is absent and the URL is left unchanged.
    """

    def _get_schema_url(self, request):
        schema_url = self.url or get_relative_url(reverse(self.url_name, request=request))
        prefix = getattr(request, "_api_service_prefix", None) or settings.URL_PREFIX
        schema_url = replace_api_root(schema_url, prefix)
        return set_query_parameters(
            url=schema_url,
            lang=request.GET.get("lang"),
            version=request.GET.get("version"),
        )
