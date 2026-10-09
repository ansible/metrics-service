"""Redirect views that respect the service's public API prefix."""

from django.conf import settings
from django.views.generic import RedirectView

from apps.core.url_prefix import replace_api_root


class ServicePrefixRedirectView(RedirectView):
    """Apply the request's API prefix, or configured URL_PREFIX, to redirects."""

    def get_redirect_url(self, *args, **kwargs):
        url = super().get_redirect_url(*args, **kwargs)
        if not url:
            return url

        prefix = getattr(self.request, "_api_service_prefix", None) or settings.URL_PREFIX
        return replace_api_root(url, prefix)
