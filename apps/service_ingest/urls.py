from django.urls import include, path

urlpatterns = [
    path("api/v1/ingest/", include("apps.service_ingest.v1.urls")),
]
