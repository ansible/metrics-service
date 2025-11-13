from django.db import connection
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET

"""
Health check views for Kubernetes monitoring.
"""


@require_GET
@csrf_exempt  # Safe: Read-only endpoint for Kubernetes liveness/readiness probes, secured at network/ingress level
def health_check(request):
    try:
        connection.ensure_connection()
        return JsonResponse({"status": "ok"}, status=200)

    except Exception as e:
        return JsonResponse({"status": "error", "details": {"database": str(e)}}, status=503)
