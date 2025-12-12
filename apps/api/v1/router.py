"""Router configuration for API v1 endpoints."""

from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()

router.register(r"organizations", views.OrganizationViewSet, basename="organization")
router.register(r"teams", views.TeamViewSet, basename="team")
router.register(r"users", views.UserViewSet, basename="user")
