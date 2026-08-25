from django.urls import path

from apps.service_ingest.v1.views import IngestView, RegisterView, StatusView

app_name = "service_ingest_v1"

urlpatterns = [
    path("register/", RegisterView.as_view(), name="register"),
    path("events/", IngestView.as_view(), name="events"),
    path("status/", StatusView.as_view(), name="status"),
]
