"""OpenAPI schema views with request-aware public API paths."""

from drf_spectacular.views import SpectacularAPIView

from apps.core.url_prefix import replace_api_root


class MetricsSpectacularAPIView(SpectacularAPIView):
    """Translate schema path keys to the public API root for prefixed requests."""

    def _get_schema_response(self, request):
        response = super()._get_schema_response(request)
        public_api_root = getattr(request, "_api_service_prefix", None)
        if public_api_root:
            response.data["paths"] = {
                replace_api_root(path, public_api_root): path_item for path, path_item in response.data["paths"].items()
            }
        return response
