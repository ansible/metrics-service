from django.urls import include, path
from drf_spectacular.views import SpectacularRedocView

from .v1 import urls as v1_urls
from .views import HealthView, MetricsSpectacularAPIView, MetricsSpectacularSwaggerView, PingView

urlpatterns = [
    path("ping/", PingView.as_view(), name="ping"),
    path("health/", HealthView.as_view(), name="health"),
    path("api/v1/", include(v1_urls)),
    # OpenAPI / Swagger UI docs.
    # DAB's ansible_base.api_documentation is excluded from dynamic URL
    # registration (via ANSIBLE_BASE_APPS_EXCLUDE_VIEW_LIST) so we register
    # prefix-aware schema and Swagger views. The schema view replaces only
    # /api in path keys, preserving /v1/... under URL_PREFIX.
    path("api/v1/docs/schema/", MetricsSpectacularAPIView.as_view(), name="schema"),
    path("api/v1/docs/", MetricsSpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/v1/docs/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
]
