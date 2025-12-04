"""
Dashboard views for task management and monitoring.

NOTE: The dashboard is only accessible when DEVELOPER_MODE_ENABLED is True.
"""

from functools import wraps

from django.conf import settings
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden
from django.shortcuts import render
from django.views.decorators.http import require_safe


def require_developer_mode(view_func):
    """
    Decorator that restricts access to views when developer mode is disabled.

    Returns 403 Forbidden with a descriptive message when DEVELOPER_MODE_ENABLED is False.
    """

    @wraps(view_func)
    def wrapper(request: HttpRequest, *args, **kwargs) -> HttpResponse:
        developer_mode = getattr(settings, "DEVELOPER_MODE_ENABLED", False)
        if not developer_mode:
            return HttpResponseForbidden(
                "The dashboard is only available when developer mode is enabled. "
                "Set METRICS_SERVICE_DEVELOPER_MODE_ENABLED=true to enable."
            )
        return view_func(request, *args, **kwargs)

    return wrapper


@require_safe
@require_developer_mode
def dashboard_view(request: HttpRequest) -> HttpResponse:
    """
    Main dashboard view for task management.

    This view renders the task dashboard interface with real-time
    task monitoring and management capabilities. All task data is
    fetched dynamically from the database via API endpoints.

    NOTE: Only accessible when DEVELOPER_MODE_ENABLED is True.

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
