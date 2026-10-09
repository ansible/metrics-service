"""OpenAPI generation with the service's request-aware public API prefix."""

from django.conf import settings
from drf_spectacular.generators import SchemaGenerator

from apps.core.url_prefix import replace_api_root


def replace_openapi_api_paths(result, public_api_root):
    """Map schema path keys to a public API root, preserving their suffixes."""
    if public_api_root:
        result["paths"] = {
            replace_api_root(path, public_api_root): path_item for path, path_item in result["paths"].items()
        }
    return result


class MetricsSchemaGenerator(SchemaGenerator):
    """Apply the API root after normal DAB and drf-spectacular schema hooks."""

    def get_schema(self, request=None, public=False):
        schema = super().get_schema(request=request, public=public)
        # Offline generation uses URL_PREFIX; live mounted requests use the
        # prefix recorded by middleware. Unmounted live requests stay canonical.
        public_api_root = settings.URL_PREFIX if request is None else getattr(request, "_api_service_prefix", None)
        return replace_openapi_api_paths(schema, public_api_root)
