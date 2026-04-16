"""Integration tests for the dashboard report PDF export endpoint."""

import datetime
from unittest.mock import patch
from urllib.parse import urlencode

import pytest
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from apps.dashboard_reports.models import JobData, JobStatusChoices, TemplateMetadata
from tests.test_utils import get_test_password

User = get_user_model()

FAKE_PDF = b"%PDF-fake"


def _make_superuser(username: str = "pdfuser") -> User:
    return User.objects.create_superuser(
        username=username, email=f"{username}@example.com", password=get_test_password()
    )


def _make_regular_user(username: str = "regularuser") -> User:
    return User.objects.create_user(
        username=username,
        email=f"{username}@example.com",
        password=get_test_password(),
        is_superuser=False,
        is_staff=False,
    )


def _seed_job_data() -> None:
    tm = TemplateMetadata.objects.create(
        template_id=1,
        template_name="Integration Template",
        time_taken_manually_execute_minutes=30,
        time_taken_create_automation_minutes=10,
    )
    now = datetime.datetime.now(datetime.UTC)
    JobData.objects.create(
        job_id=1,
        template_id=1,
        template_name="Integration Template",
        organization_id=1,
        project_id=1,
        project_name="Integration Project",
        status=JobStatusChoices.SUCCESSFUL,
        started=now - datetime.timedelta(hours=2),
        finished=now - datetime.timedelta(hours=1),
        elapsed=120,
        num_hosts=5,
        template_metadata=tm,
    )


def _fake_weasyprint(*args, **kwargs):
    """Return a minimal fake PDF response instead of rendering."""
    from django.http import HttpResponse

    report_type = kwargs.get("context", {}).get("report_type", "summary")
    response = HttpResponse(content=FAKE_PDF, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="automation-dashboard-{report_type}-2026-04-16.pdf"'
    return response


def _get_pdf(client, params: dict):
    """GET the export endpoint with params encoded in the query string."""
    url = reverse("dashboard_reports:report-export")
    qs = urlencode(params, doseq=True)
    with patch("apps.dashboard_reports.viewsets.dashboard_report.WeasyTemplateResponse", side_effect=_fake_weasyprint):
        return client.get(f"{url}?{qs}")


@pytest.mark.integration
class TestExportPDFAccess(TestCase):
    """Verify RBAC and method restrictions on PDF export."""

    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.superuser = _make_superuser()
        self.regular_user = _make_regular_user()
        self.base_params = {"period": "last_7_days", "tz": "UTC", "report_type": "summary", "export_format": "pdf"}

    def test_unauthenticated_returns_403(self):
        response = _get_pdf(self.client, self.base_params)
        assert response.status_code == 403

    def test_regular_user_returns_403(self):
        self.client.force_authenticate(user=self.regular_user)
        response = _get_pdf(self.client, self.base_params)
        assert response.status_code == 403

    def test_superuser_pdf_get_returns_200(self):
        self.client.force_authenticate(user=self.superuser)
        response = _get_pdf(self.client, self.base_params)
        assert response.status_code == 200

    def test_put_not_allowed(self):
        self.client.force_authenticate(user=self.superuser)
        response = self.client.put(reverse("dashboard_reports:report-export"), data={})
        assert response.status_code == 405

    def test_delete_not_allowed(self):
        self.client.force_authenticate(user=self.superuser)
        response = self.client.delete(reverse("dashboard_reports:report-export"))
        assert response.status_code == 405


@pytest.mark.integration
class TestExportPDFResponseContract(TestCase):
    """Verify response headers for each PDF report_type."""

    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.superuser = _make_superuser()
        self.client.force_authenticate(user=self.superuser)
        _seed_job_data()

    def _post_pdf(self, report_type: str, **extra_params):
        params = {"period": "last_7_days", "tz": "UTC", "report_type": report_type, "export_format": "pdf"}
        params.update(extra_params)
        return _get_pdf(self.client, params)

    # --- Content-Type ---

    def test_summary_content_type_is_pdf(self):
        response = self._post_pdf("summary")
        assert response.status_code == 200
        assert "application/pdf" in response["Content-Type"]

    def test_roi_content_type_is_pdf(self):
        response = self._post_pdf("roi")
        assert response.status_code == 200
        assert "application/pdf" in response["Content-Type"]

    def test_trends_content_type_is_pdf(self):
        response = self._post_pdf("trends")
        assert response.status_code == 200
        assert "application/pdf" in response["Content-Type"]

    # --- Content-Disposition ---

    def test_summary_content_disposition_is_attachment(self):
        response = self._post_pdf("summary")
        assert "attachment" in response["Content-Disposition"]
        assert "summary" in response["Content-Disposition"]
        assert ".pdf" in response["Content-Disposition"]

    def test_roi_content_disposition_is_attachment(self):
        response = self._post_pdf("roi")
        assert "attachment" in response["Content-Disposition"]
        assert "roi" in response["Content-Disposition"]
        assert ".pdf" in response["Content-Disposition"]

    def test_trends_content_disposition_is_attachment(self):
        response = self._post_pdf("trends")
        assert "attachment" in response["Content-Disposition"]
        assert "trends" in response["Content-Disposition"]
        assert ".pdf" in response["Content-Disposition"]

    # --- Error cases ---

    def test_missing_period_returns_400(self):
        url = reverse("dashboard_reports:report-export")
        qs = urlencode({"tz": "UTC", "report_type": "summary", "export_format": "pdf"})
        with patch(
            "apps.dashboard_reports.viewsets.dashboard_report.WeasyTemplateResponse", side_effect=_fake_weasyprint
        ):
            response = self.client.get(f"{url}?{qs}")
        assert response.status_code == 400

    def test_invalid_period_returns_400(self):
        url = reverse("dashboard_reports:report-export")
        qs = urlencode({"period": "last_999_days", "tz": "UTC", "report_type": "summary", "export_format": "pdf"})
        with patch(
            "apps.dashboard_reports.viewsets.dashboard_report.WeasyTemplateResponse", side_effect=_fake_weasyprint
        ):
            response = self.client.get(f"{url}?{qs}")
        assert response.status_code == 400

    def test_invalid_report_type_returns_400(self):
        url = reverse("dashboard_reports:report-export")
        qs = urlencode({"period": "last_7_days", "tz": "UTC", "report_type": "invalid", "export_format": "pdf"})
        with patch(
            "apps.dashboard_reports.viewsets.dashboard_report.WeasyTemplateResponse", side_effect=_fake_weasyprint
        ):
            response = self.client.get(f"{url}?{qs}")
        assert response.status_code == 400

    # --- Filters accepted ---

    def test_organization_filter_accepted(self):
        response = self._post_pdf("summary", organization=1)
        assert response.status_code == 200

    def test_organization_filter_on_roi(self):
        response = self._post_pdf("roi", organization=1)
        assert response.status_code == 200

    def test_organization_filter_on_trends(self):
        response = self._post_pdf("trends", organization=1)
        assert response.status_code == 200
