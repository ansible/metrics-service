from django.urls import include, path

app_name = "service_ingest"

urlpatterns = [
    path("api/v1/ingest/", include("apps.service_ingest.v1.urls", namespace="v1")),
]
