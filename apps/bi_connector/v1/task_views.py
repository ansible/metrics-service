"""
BI connector task status endpoint.

Provides a scoped, token-authenticated view for polling the status of BI
collection tasks dispatched by ControllerTimeSeriesView.  Only tasks with
function_name == "collect_bi_controller_data" are accessible here — the
full task management API (/api/v1/tasks/) requires DeveloperModeRequired.
"""

import logging

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .mixins import BiConnectorEnabledMixin

logger = logging.getLogger(__name__)

_BI_FUNCTION_NAME = "collect_bi_controller_data"


class BiTaskStatusView(BiConnectorEnabledMixin, APIView):
    """
    Return the status and result of a single BI collection task.

    Only tasks created by the BI connector (function_name == "collect_bi_controller_data")
    are accessible.  Any other task_id returns 404 to avoid leaking information about
    unrelated system tasks.

    Poll until status is "completed" or "failed", then read result_data.
    """

    permission_classes = [IsAuthenticated]
    versioning_class = None

    def get(self, request, task_id: int) -> Response:
        """Return status and result for the given BI collection task ID."""
        from apps.tasks.models import Task

        try:
            task = Task.objects.get(pk=task_id, function_name=_BI_FUNCTION_NAME, created_by=request.user)
        except Task.DoesNotExist as exc:
            from rest_framework.exceptions import NotFound

            raise NotFound() from exc

        return Response(
            {
                "task_id": task.id,
                "status": task.status,
                "collector_type": (task.task_data or {}).get("collector_key"),
                "since": (task.task_data or {}).get("since"),
                "until": (task.task_data or {}).get("until"),
                "result_data": task.result_data if task.status == "completed" else None,
                "error_message": task.error_message if task.status == "failed" else None,
                "created": task.created.isoformat() if task.created else None,
                "completed_at": task.completed_at.isoformat() if task.completed_at else None,
            }
        )
