"""
Dashboard views for task management and monitoring.
"""

from django.conf import settings
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_safe


def url_for(path):
    """
    Transforms URL paths to use METRICS_SERVICE_URL_PREFIX, if present
    When settings.URL_PREFIX is None, returns path prefixed with /api/
    When settings.URL_PREFIX is set, returns path prefixed with /$prefix/, after slash sanitization
    Preserves the trailing-slash state of the input path.
    Uses string join (no regex) to avoid reDOS from unsanitized input.
    """
    prefix = settings.URL_PREFIX or "/api/"
    trailing_slash = path.endswith("/")
    segments = [x for x in f"{prefix}/{path}".split("/") if x]
    base = "/" + "/".join(segments) if segments else "/"
    return base + "/" if trailing_slash else base


@require_safe
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
        "api_base_url": url_for("/v1/"),  # /api/v1/ or /URL_PREFIX/v1/
        "user": request.user,
        "available_functions": list(TASK_FUNCTIONS.keys()),
        "database_driven": True,  # Flag to indicate this uses database tasks
    }

    return render(request, "dashboard.html", context)
