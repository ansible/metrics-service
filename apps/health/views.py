from django.db import connection
from django.http import JsonResponse
from django.views.decorators.http import require_GET

"""
Health check views for Kubernetes monitoring.
"""


@require_GET
def health_check(request):
    try:
        connection.ensure_connection()
        return JsonResponse({"status": "ok"}, status=200)

    except Exception as e:
        return JsonResponse({"status": "error", "details": {"database": str(e)}}, status=503)
