"""
Tests for apps/bi_connector/v1/collector_settings_views.py
"""

import json
from unittest.mock import patch

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.bi_connector.models import CollectionBatch
from apps.bi_connector.v1.collector_settings_views import AVAILABLE_BACKFILL_COLLECTORS
from apps.core.models import User
from apps.dynamic_settings.models import Setting
from tests.test_utils import get_test_password

_SUBMIT_PATCH = "apps.tasks.tasks_system.submit_task_to_dispatcher"

COLLECTOR_SETTINGS_URL = "bi_connector:collector-settings:collector-settings"
ADMIN_BATCHES_URL = "bi_connector:collector-settings:admin-batches-list"


@pytest.mark.unit
@pytest.mark.django_db
class TestCollectorSettingsView(APITestCase):
    """Tests for GET/PATCH /api/v1/bi/collector-settings/."""

    def setUp(self):
        self.user = User.objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password=get_test_password(),
        )
        self.url = reverse(COLLECTOR_SETTINGS_URL)
        # Remove the auto-seeded BI_CONNECTOR_COLLECTORS setting so tests start clean
        Setting.objects.filter(setting_key="BI_CONNECTOR_COLLECTORS").delete()

    def test_get_returns_settings_when_none_exist(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["setting_key"] == "BI_CONNECTOR_COLLECTORS"
        assert response.data["current_value"] is None

    def test_get_returns_settings_when_set(self):
        Setting.objects.update_or_create(
            setting_key="BI_CONNECTOR_COLLECTORS",
            defaults={"current_value": json.dumps({"main_host": True})},
        )
        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["current_value"] == {"main_host": True}

    def test_get_returns_available_collectors_list(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.url)
        assert response.status_code == status.HTTP_200_OK
        assert "available_collectors" in response.data
        assert isinstance(response.data["available_collectors"], list)
        assert len(response.data["available_collectors"]) > 0
        assert "unified_jobs" in response.data["available_collectors"]

    def test_get_returns_all_available_collectors(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.url)
        for collector in AVAILABLE_BACKFILL_COLLECTORS:
            assert collector in response.data["available_collectors"]

    def test_get_returns_null_for_corrupted_json_setting(self):
        Setting.objects.update_or_create(
            setting_key="BI_CONNECTOR_COLLECTORS",
            defaults={"current_value": "not-valid-json"},
        )
        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["current_value"] is None

    def test_patch_valid_data_saves_setting(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.patch(self.url, {"main_host": True}, format="json")
        assert response.status_code == status.HTTP_200_OK
        setting = Setting.objects.get(setting_key="BI_CONNECTOR_COLLECTORS")
        assert json.loads(setting.current_value) == {"main_host": True}

    def test_patch_updates_existing_setting(self):
        Setting.objects.update_or_create(
            setting_key="BI_CONNECTOR_COLLECTORS",
            defaults={"current_value": json.dumps({"main_host": False})},
        )
        self.client.force_authenticate(user=self.user)
        self.client.patch(self.url, {"main_host": True}, format="json")
        setting = Setting.objects.get(setting_key="BI_CONNECTOR_COLLECTORS")
        assert json.loads(setting.current_value) == {"main_host": True}

    def test_patch_returns_updated_current_value(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.patch(self.url, {"main_host": True, "unified_jobs": False}, format="json")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["current_value"] == {"main_host": True, "unified_jobs": False}

    def test_patch_unknown_collector_returns_400(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.patch(self.url, {"nonexistent_collector": True}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Unknown collector" in str(response.data["detail"])

    def test_patch_non_bool_value_returns_400(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.patch(self.url, {"main_host": "yes"}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "boolean" in str(response.data["detail"]).lower()

    def test_patch_non_dict_body_returns_400(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.patch(self.url, ["main_host"], format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_patch_integer_value_returns_400(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.patch(self.url, {"main_host": 1}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_unauthenticated_get_returns_401_or_403(self):
        response = self.client.get(self.url)
        assert response.status_code in [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN]

    def test_unauthenticated_patch_returns_401_or_403(self):
        response = self.client.patch(self.url, {"main_host": True}, format="json")
        assert response.status_code in [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN]

    def test_setting_key_always_in_response(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.url)
        assert response.data["setting_key"] == "BI_CONNECTOR_COLLECTORS"


@pytest.mark.unit
@pytest.mark.django_db
class TestAdminCollectionBatchViewSet(APITestCase):
    """Tests for GET/POST /api/v1/bi/collector-settings/batches/."""

    def setUp(self):
        self.user = User.objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password=get_test_password(),
        )
        self.url = reverse(ADMIN_BATCHES_URL)

    def test_list_returns_batches(self):
        CollectionBatch.objects.create(
            collector_type="unified_jobs",
            batch_type="backfill",
            status="completed",
        )
        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.url)
        assert response.status_code == status.HTTP_200_OK
        # DRF list view returns either a list or paginated result
        results = response.data if isinstance(response.data, list) else response.data.get("results", response.data)
        assert len(results) >= 1

    def test_list_returns_200_empty(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.url)
        assert response.status_code == status.HTTP_200_OK

    def test_create_missing_collector_type_returns_400(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.post(self.url, {}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "collector_type" in str(response.data["detail"])

    def test_create_unknown_collector_type_returns_400(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.post(
            self.url,
            {"collector_type": "does_not_exist"},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Unknown collector_type" in str(response.data["detail"])

    def test_create_time_series_missing_since_returns_400(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.post(
            self.url,
            {"collector_type": "unified_jobs"},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "since" in str(response.data["detail"]) or "until" in str(response.data["detail"])

    def test_create_time_series_missing_until_returns_400(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.post(
            self.url,
            {"collector_type": "unified_jobs", "since": "2025-03-01T00:00:00Z"},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_create_snapshot_collector_no_dates_required(self):
        self.client.force_authenticate(user=self.user)
        with patch(_SUBMIT_PATCH):
            response = self.client.post(
                self.url,
                {"collector_type": "config"},
                format="json",
            )
        assert response.status_code == status.HTTP_202_ACCEPTED

    def test_create_billing_collector_dispatches_collect_bi_billing_data_task(self):
        self.client.force_authenticate(user=self.user)
        with patch(_SUBMIT_PATCH):
            self.client.post(
                self.url,
                {
                    "collector_type": "main_host",
                    "since": "2025-03-01T00:00:00Z",
                    "until": "2025-03-07T00:00:00Z",
                },
                format="json",
            )
        from apps.tasks.models import Task

        task = Task.objects.filter(function_name="collect_bi_billing_data").first()
        assert task is not None
        assert task.task_data["collector_type"] == "main_host"

    def test_create_backfill_collector_dispatches_backfill_bi_collector_task(self):
        self.client.force_authenticate(user=self.user)
        with patch(_SUBMIT_PATCH):
            self.client.post(
                self.url,
                {
                    "collector_type": "unified_jobs",
                    "since": "2025-03-01T00:00:00Z",
                    "until": "2025-03-07T00:00:00Z",
                },
                format="json",
            )
        from apps.tasks.models import Task

        task = Task.objects.filter(function_name="backfill_bi_collector").first()
        assert task is not None
        assert task.task_data["collector_type"] == "unified_jobs"

    def test_create_returns_202(self):
        self.client.force_authenticate(user=self.user)
        with patch(_SUBMIT_PATCH):
            response = self.client.post(
                self.url,
                {
                    "collector_type": "unified_jobs",
                    "since": "2025-03-01T00:00:00Z",
                    "until": "2025-03-07T00:00:00Z",
                },
                format="json",
            )
        assert response.status_code == status.HTTP_202_ACCEPTED

    def test_create_creates_collection_batch_record(self):
        self.client.force_authenticate(user=self.user)
        with patch(_SUBMIT_PATCH):
            self.client.post(
                self.url,
                {
                    "collector_type": "unified_jobs",
                    "since": "2025-03-01T00:00:00Z",
                    "until": "2025-03-07T00:00:00Z",
                },
                format="json",
            )
        assert CollectionBatch.objects.filter(collector_type="unified_jobs").exists()

    def test_create_calls_submit_task_to_dispatcher(self):
        self.client.force_authenticate(user=self.user)
        with patch(_SUBMIT_PATCH) as mock_submit:
            self.client.post(
                self.url,
                {
                    "collector_type": "unified_jobs",
                    "since": "2025-03-01T00:00:00Z",
                    "until": "2025-03-07T00:00:00Z",
                },
                format="json",
            )
        mock_submit.assert_called_once()

    def test_unauthenticated_list_returns_401_or_403(self):
        response = self.client.get(self.url)
        assert response.status_code in [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN]

    def test_unauthenticated_create_returns_401_or_403(self):
        response = self.client.post(
            self.url,
            {"collector_type": "unified_jobs"},
            format="json",
        )
        assert response.status_code in [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN]

    def test_batch_response_includes_collector_type(self):
        self.client.force_authenticate(user=self.user)
        with patch(_SUBMIT_PATCH):
            response = self.client.post(
                self.url,
                {
                    "collector_type": "config",
                },
                format="json",
            )
        assert response.status_code == status.HTTP_202_ACCEPTED
        assert response.data["collector_type"] == "config"

    def test_main_host_daily_is_billing_collector(self):
        """main_host_daily should dispatch collect_bi_billing_data, not backfill."""
        self.client.force_authenticate(user=self.user)
        with patch(_SUBMIT_PATCH):
            self.client.post(
                self.url,
                {
                    "collector_type": "main_host_daily",
                    "since": "2025-03-01T00:00:00Z",
                    "until": "2025-03-07T00:00:00Z",
                },
                format="json",
            )
        from apps.tasks.models import Task

        task = Task.objects.filter(function_name="collect_bi_billing_data").first()
        assert task is not None

    def test_snapshot_collector_does_not_create_task_with_wrong_function(self):
        """Snapshot (non-billing) collectors should dispatch backfill_bi_collector."""
        self.client.force_authenticate(user=self.user)
        with patch(_SUBMIT_PATCH):
            self.client.post(
                self.url,
                {"collector_type": "execution_environments"},
                format="json",
            )
        from apps.tasks.models import Task

        task = Task.objects.filter(function_name="backfill_bi_collector").first()
        assert task is not None
