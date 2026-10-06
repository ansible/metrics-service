"""OpenAPI post-processing for the service's public API prefix."""

from django.conf import settings

from apps.core.url_prefix import replace_api_root


def replace_openapi_api_root(result, generator, request, public, **kwargs):
    """Map schema paths to the public API root for mounted requests and syncs.

    Live requests use the prefix recorded by ServicePrefixMiddleware. Offline
    schema generation (used by the central OpenAPI sync) uses URL_PREFIX from
    its environment. An unprefixed live request stays on the local /api/v1 root.
    """
    public_api_root = settings.URL_PREFIX if request is None else getattr(request, "_api_service_prefix", None)

    if public_api_root:
        result["paths"] = {
            replace_api_root(path, public_api_root): path_item for path, path_item in result["paths"].items()
        }
    return result
