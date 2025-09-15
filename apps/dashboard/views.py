"""
Dashboard views for task management and monitoring.
"""

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render


def dashboard_view(request: HttpRequest) -> HttpResponse:
    """
    Main dashboard view for task management.

    This view renders the task dashboard interface with real-time
    task monitoring and management capabilities. All task data is
    fetched dynamically from the database via API endpoints.

    Args:
        request: HTTP request object

    Returns:
        HttpResponse: Rendered dashboard template
    """
    from apps.tasks.tasks import TASK_FUNCTIONS

    context = {
        "page_title": "Task Dashboard",
        "api_base_url": "/api/v1/",
        "user": request.user,
        "available_functions": list(TASK_FUNCTIONS.keys()),
        "database_driven": True,  # Flag to indicate this uses database tasks
    }
    return render(request, "dashboard.html", context)
