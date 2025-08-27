"""
URL configuration for API v1.
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import AnimalViewSet, OrganizationViewSet, TeamViewSet, UserViewSet

app_name = "v1"

# Create DRF router
router = DefaultRouter()
router.register(r"users", UserViewSet, basename="user")
router.register(r"organizations", OrganizationViewSet, basename="organization")
router.register(r"teams", TeamViewSet, basename="team")
router.register(r"animals", AnimalViewSet, basename="animal")

urlpatterns = [
    # Include router URLs
    path("", include(router.urls)),
]
