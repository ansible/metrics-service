"""
URL configuration for API v1.
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import OrganizationViewSet, UserViewSet

app_name = "v1"

# Create DRF router
router = DefaultRouter()
router.register(r"users", UserViewSet, basename="user")
router.register(r"organizations", OrganizationViewSet, basename="organization")

urlpatterns = [
    # Include router URLs
    path("", include(router.urls)),
]
