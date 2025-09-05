"""
Dashboard views for task management and monitoring.
"""

from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse


def dashboard_view(request: HttpRequest) -> HttpResponse:
    """
    Main dashboard view for task management.

    This view renders the task dashboard interface with real-time
    task monitoring and management capabilities.

    Args:
        request: HTTP request object

    Returns:
        HttpResponse: Rendered dashboard template
    """
    context = {
        "page_title": "Task Dashboard",
        "api_base_url": "/api/v1/",
        "user": request.user,
    }
    return render(request, "dashboard.html", context)
