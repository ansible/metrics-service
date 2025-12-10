"""
Core app URLs including authentication and health endpoints.
"""

from django.contrib.auth import views as auth_views
from django.urls import path

from .views import HealthView, PingView

urlpatterns = [
    # Health endpoints
    path("ping/", PingView.as_view(), name="ping"),
    path("health/", HealthView.as_view(), name="health"),
    # Authentication URLs
    path("login/", auth_views.LoginView.as_view(template_name="registration/login.html"), name="login"),
    path("logout/", auth_views.LogoutView.as_view(next_page="/login/"), name="logout"),
]
