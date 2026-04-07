"""
DB-backed tests for TemplateMetadataViewSet.

These tests verify the full round-trip: the viewset actually persists changes
and reverts to system defaults correctly. No mocking of ORM calls.
"""

import pytest
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.core.models import User
from apps.dashboard_reports.models import TemplateMetadata


def _create_metadata(
    template_id: int = 42,
    template_name: str = "Test Template",
    time_taken_manually_execute_minutes: int | None = 30,
    time_taken_create_automation_minutes: int | None = 60,
) -> TemplateMetadata:
    return TemplateMetadata.objects.create(
        template_id=template_id,
        template_name=template_name,
        time_taken_manually_execute_minutes=time_taken_manually_execute_minutes,
        time_taken_create_automation_minutes=time_taken_create_automation_minutes,
    )


def _url(pk: int) -> str:
    return reverse("dashboard_reports:template-metadata", kwargs={"pk": pk})


@pytest.mark.integration
@pytest.mark.django_db
@override_settings(MODE="development")
class TestTemplateMetadataPutPatchDb(TestCase):
    """Verify PUT actually persists updated values to the DB."""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username="testuser", password="pass")
        self.client.force_authenticate(user=self.user)
        self.instance = _create_metadata()

    def test_put_updates_time_fields_in_db(self):
        response = self.client.put(
            _url(self.instance.template_id),
            data={
                "time_taken_manually_execute_minutes": 99,
                "time_taken_create_automation_minutes": 199,
            },
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK

        self.instance.refresh_from_db()
        assert self.instance.time_taken_manually_execute_minutes == 99
        assert self.instance.time_taken_create_automation_minutes == 199

    def test_put_response_reflects_updated_values(self):
        response = self.client.put(
            _url(self.instance.template_id),
            data={
                "time_taken_manually_execute_minutes": 55,
                "time_taken_create_automation_minutes": 110,
            },
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["time_taken_manually_execute_minutes"] == 55
        assert response.data["time_taken_create_automation_minutes"] == 110

    def test_put_with_null_sets_fields_to_null_in_db(self):
        response = self.client.put(
            _url(self.instance.template_id),
            data={
                "time_taken_manually_execute_minutes": None,
                "time_taken_create_automation_minutes": None,
            },
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK

        self.instance.refresh_from_db()
        assert self.instance.time_taken_manually_execute_minutes is None
        assert self.instance.time_taken_create_automation_minutes is None

    def test_put_does_not_change_template_id(self):
        original_template_id = self.instance.template_id

        self.client.put(
            _url(self.instance.template_id),
            data={
                "template_id": 999,
                "time_taken_manually_execute_minutes": 10,
                "time_taken_create_automation_minutes": 20,
            },
            format="json",
        )

        self.instance.refresh_from_db()
        assert self.instance.template_id == original_template_id

    def test_put_returns_404_for_nonexistent_pk(self):
        response = self.client.put(
            _url(99999),
            data={
                "time_taken_manually_execute_minutes": 10,
                "time_taken_create_automation_minutes": 20,
            },
            format="json",
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_patch_updates_only_provided_field(self):
        response = self.client.patch(
            _url(self.instance.template_id),
            data={
                "time_taken_manually_execute_minutes": 77,
            },
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK

        self.instance.refresh_from_db()
        assert self.instance.time_taken_manually_execute_minutes == 77
        assert self.instance.time_taken_create_automation_minutes == 60  # unchanged


@pytest.mark.integration
@pytest.mark.django_db
@override_settings(MODE="development")
class TestTemplateMetadataDeleteDb(TestCase):
    """Verify DELETE reverts overrides to NULL (system defaults) without deleting the record."""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username="testuser", password="pass")
        self.client.force_authenticate(user=self.user)
        self.instance = _create_metadata(
            time_taken_manually_execute_minutes=30,
            time_taken_create_automation_minutes=60,
        )

    def test_delete_sets_time_fields_to_null_in_db(self):
        response = self.client.delete(_url(self.instance.template_id))

        assert response.status_code == status.HTTP_204_NO_CONTENT

        self.instance.refresh_from_db()
        assert self.instance.time_taken_manually_execute_minutes is None
        assert self.instance.time_taken_create_automation_minutes is None

    def test_delete_does_not_remove_the_record(self):
        pk = self.instance.pk
        self.client.delete(_url(pk))

        assert TemplateMetadata.objects.filter(pk=pk).exists()

    def test_delete_preserves_template_id_and_name(self):
        original_template_id = self.instance.template_id
        original_template_name = self.instance.template_name

        self.client.delete(_url(self.instance.template_id))

        self.instance.refresh_from_db()
        assert self.instance.template_id == original_template_id
        assert self.instance.template_name == original_template_name

    def test_get_after_delete_reflects_null_overrides(self):
        self.client.delete(_url(self.instance.template_id))

        response = self.client.get(_url(self.instance.template_id))

        assert response.status_code == status.HTTP_200_OK
        assert response.data["time_taken_manually_execute_minutes"] is None
        assert response.data["time_taken_create_automation_minutes"] is None

    def test_delete_returns_404_for_nonexistent_pk(self):
        response = self.client.delete(_url(99999))

        assert response.status_code == status.HTTP_404_NOT_FOUND
