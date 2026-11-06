"""
End-to-end (in-process) request ID propagation test.

Covers the full path: API request -> Task.request_id -> dispatcherd payload ->
worker log records.
"""

import logging
import uuid
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APITestCase

from apps.core.logging_filters import RequestIdFilter
from apps.tasks.models import Task
from apps.tasks.tasks import submit_task_to_dispatcher
from apps.tasks.tasks_system import execute_db_task
from tests.test_utils import get_test_password

User = get_user_model()


class _RecordingHandler(logging.Handler):
    """Collect log records for assertions."""

    def __init__(self):
        super().__init__()
        self.records = []

    def emit(self, record):
        self.records.append(record)


@pytest.mark.unit
@pytest.mark.django_db
class TestRequestIdPropagation(APITestCase):
    """A request ID survives the API, the Task row, the payload and the worker."""

    def setUp(self):
        self.user = User.objects.create_superuser(
            username="propagation-admin", email="admin@example.com", password=get_test_password()
        )
        self.client.force_authenticate(user=self.user)

    def test_request_id_flows_from_api_to_worker_logs(self):
        request_id = str(uuid.uuid4())
        url = reverse("tasks:v1:task-schedule-immediate")

        with (
            patch("dispatcherd.publish.submit_task") as mock_submit,
            patch("apps.tasks.dispatcherd_config.ensure_dispatcherd_configured"),
            patch("apps.tasks.tasks.get_queue_for_function", return_value="metrics"),
        ):
            response = self.client.post(
                url,
                {"name": "Propagation Task", "function_name": "hello_world", "task_data": {}},
                format="json",
                HTTP_X_REQUEST_ID=request_id,
            )

            assert response.status_code == 200
            assert response["X-Request-ID"] == request_id

            task = Task.objects.get(id=response.data["task_id"])
            assert task.request_id == request_id

            submit_task_to_dispatcher(task)
            mock_submit.assert_called_once()
            payload = mock_submit.call_args.kwargs["kwargs"]
            assert payload == {"task_id": task.id, "request_id": request_id}

        # The handler mirrors production wiring: the project filter is what
        # stamps the request ID onto worker records.
        handler = _RecordingHandler()
        handler.addFilter(RequestIdFilter())
        logger = logging.getLogger("apps.tasks")
        old_level, old_propagate = logger.level, logger.propagate
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
        try:
            result = execute_db_task(**payload)
        finally:
            logger.removeHandler(handler)
            logger.setLevel(old_level)
            logger.propagate = old_propagate

        assert result["status"] == "success"
        assert handler.records, "worker produced no log records"
        assert all(record.request_id == request_id for record in handler.records)
