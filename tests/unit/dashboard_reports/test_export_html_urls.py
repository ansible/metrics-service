"""Unit tests for DashboardReportViewSet HTML export endpoint (summary, roi, trends)."""

import datetime
import decimal
from unittest.mock import patch
from urllib.parse import urlencode

import pytest
from django.urls import reverse

from apps.dashboard_reports.models import (
    JobData,
    JobStatusChoices,
    SubscriptionCost,
    TemplateMetadata,
)

FIXED_PER_SECOND_COST = decimal.Decimal("0.001")


def get_now() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


def build_html_query(report_type: str = "summary", days_back: int = 14, **extra) -> dict:
    query = {
        "period": f"last_{days_back}_days",
        "tz": "UTC",
        "report_type": report_type,
        "export_format": "html",
    }
    query.update(extra)
    return query


def get_html(client, params: dict):
    url = reverse("dashboard_reports:report-export")
    qs = urlencode(params, doseq=True)
    return client.get(f"{url}?{qs}")


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def template_metadata():
    templates = [
        TemplateMetadata(
            template_id=1,
            template_name="Template A",
            time_taken_manually_execute_minutes=240,
            time_taken_create_automation_minutes=40,
        ),
        TemplateMetadata(
            template_id=2,
            template_name="Template B",
            time_taken_manually_execute_minutes=360,
            time_taken_create_automation_minutes=60,
        ),
    ]
    return TemplateMetadata.objects.bulk_create(templates)


@pytest.fixture
def job_data(template_metadata):
    # Anchor to noon UTC yesterday so timestamps are always in the past
    now = (get_now() - datetime.timedelta(days=1)).replace(hour=12, minute=0, second=0, microsecond=0)
    job_configs = [
        (1, 0, 1, 10, "Project A", JobStatusChoices.SUCCESSFUL, datetime.timedelta(minutes=5), 60, 10, 1, "test_user"),
        (2, 0, 1, 10, "Project A", JobStatusChoices.FAILED, datetime.timedelta(minutes=1), 5, 10, 1, "test_user"),
        (
            3,
            1,
            2,
            20,
            "Project B",
            JobStatusChoices.FAILED,
            datetime.timedelta(days=7, hours=1),
            50,
            1,
            2,
            "other_user",
        ),
        (
            4,
            1,
            2,
            20,
            "Project B",
            JobStatusChoices.SUCCESSFUL,
            datetime.timedelta(days=7, hours=2),
            300,
            1,
            2,
            "other_user",
        ),
    ]
    jobs = []
    for job_id, tmpl_idx, org_id, proj_id, proj_name, status, offset, elapsed, hosts, user_id, username in job_configs:
        tmpl = template_metadata[tmpl_idx]
        jobs.append(
            JobData(
                job_id=job_id,
                template_name=tmpl.template_name,
                template_id=tmpl.template_id,
                project_id=proj_id,
                project_name=proj_name,
                organization_id=org_id,
                status=status,
                started=now - offset - datetime.timedelta(minutes=10),
                finished=now - offset,
                elapsed=elapsed,
                num_hosts=hosts,
                launched_by_id=user_id,
                launched_by_username=username,
                template_metadata=tmpl,
            )
        )
    return JobData.objects.bulk_create(jobs)


# =============================================================================
# Access / RBAC
# =============================================================================


@pytest.mark.unit
@pytest.mark.django_db
class TestExportHTMLAccess:
    """RBAC and method restrictions on the HTML export endpoint."""

    def test_unauthenticated_returns_403(self, api_client):
        response = get_html(api_client, build_html_query())
        assert response.status_code == 403

    def test_superuser_returns_200(self, admin_client):
        response = get_html(admin_client, build_html_query())
        assert response.status_code == 200

    def test_post_not_allowed(self, admin_client):
        url = reverse("dashboard_reports:report-export")
        response = admin_client.post(url, data={})
        assert response.status_code == 405

    def test_put_not_allowed(self, admin_client):
        url = reverse("dashboard_reports:report-export")
        response = admin_client.put(url, data={})
        assert response.status_code == 405


# =============================================================================
# Content-type and body
# =============================================================================


@pytest.mark.unit
@pytest.mark.django_db
class TestExportHTMLContentType:
    """Verify the HTML export returns text/html with rendered markup."""

    @pytest.fixture(autouse=True)
    def fixed_cost(self):
        with patch(
            "apps.dashboard_reports.models.SubscriptionCost.per_second_subscription_cost",
            return_value=FIXED_PER_SECOND_COST,
        ):
            yield

    def test_summary_content_type_is_html(self, admin_client):
        response = get_html(admin_client, build_html_query("summary"))
        assert response.status_code == 200
        assert "text/html" in response["Content-Type"]

    def test_roi_content_type_is_html(self, admin_client):
        response = get_html(admin_client, build_html_query("roi"))
        assert response.status_code == 200
        assert "text/html" in response["Content-Type"]

    def test_trends_content_type_is_html(self, admin_client):
        response = get_html(admin_client, build_html_query("trends"))
        assert response.status_code == 200
        assert "text/html" in response["Content-Type"]

    def test_no_content_disposition_attachment(self, admin_client):
        """HTML export opens inline — no attachment header."""
        response = get_html(admin_client, build_html_query("summary"))
        assert response.status_code == 200
        assert "Content-Disposition" not in response or "attachment" not in response.get("Content-Disposition", "")

    def test_response_body_is_html_document(self, admin_client):
        response = get_html(admin_client, build_html_query("summary"))
        assert response.status_code == 200
        assert b"<!DOCTYPE html>" in response.content or b"<html" in response.content

    def test_response_contains_print_button(self, admin_client):
        response = get_html(admin_client, build_html_query("summary"))
        assert response.status_code == 200
        assert b"window.print()" in response.content

    def test_response_contains_red_hat_logo(self, admin_client):
        response = get_html(admin_client, build_html_query("summary"))
        assert response.status_code == 200
        assert b"RedHatLogo" in response.content


# =============================================================================
# Summary HTML report
# =============================================================================


@pytest.mark.unit
@pytest.mark.django_db(transaction=True, reset_sequences=True)
class TestExportHTMLSummary:
    """Verify summary HTML report content."""

    @pytest.fixture(autouse=True)
    def fixed_cost(self):
        with patch(
            "apps.dashboard_reports.models.SubscriptionCost.per_second_subscription_cost",
            return_value=FIXED_PER_SECOND_COST,
        ):
            yield

    def test_summary_contains_report_title(self, job_data, admin_client):
        response = get_html(admin_client, build_html_query("summary"))
        assert response.status_code == 200
        assert b"Summary" in response.content

    def test_summary_contains_template_names(self, job_data, admin_client):
        response = get_html(admin_client, build_html_query("summary"))
        assert response.status_code == 200
        assert b"Template A" in response.content
        assert b"Template B" in response.content

    def test_summary_contains_period_badge(self, job_data, admin_client):
        response = get_html(admin_client, build_html_query("summary"))
        assert response.status_code == 200
        assert b"Period:" in response.content

    def test_summary_organization_filter_limits_templates(self, job_data, admin_client):
        """Filtering by org=1 should only include Template A in the response."""
        response = get_html(admin_client, build_html_query("summary", organization=[1]))
        assert response.status_code == 200
        assert b"Template A" in response.content
        assert b"Template B" not in response.content

    def test_summary_label_filter_shows_badge(self, job_data, admin_client):
        """label has no name lookup — exercises the else branch in _build_filter_labels."""
        response = get_html(admin_client, build_html_query("summary", label=[42]))
        assert response.status_code == 200
        assert b"Label" in response.content


# =============================================================================
# ROI HTML report
# =============================================================================


@pytest.mark.unit
@pytest.mark.django_db(transaction=True, reset_sequences=True)
class TestExportHTMLROI:
    """Verify ROI HTML report content."""

    @pytest.fixture(autouse=True)
    def fixed_cost(self):
        with patch(
            "apps.dashboard_reports.models.SubscriptionCost.per_second_subscription_cost",
            return_value=FIXED_PER_SECOND_COST,
        ):
            yield

    def test_roi_contains_report_title(self, job_data, admin_client):
        response = get_html(admin_client, build_html_query("roi"))
        assert response.status_code == 200
        assert b"ROI" in response.content

    def test_roi_contains_cost_savings_label(self, job_data, admin_client):
        response = get_html(admin_client, build_html_query("roi"))
        assert response.status_code == 200
        assert b"Cost savings" in response.content

    def test_roi_contains_period_badge(self, job_data, admin_client):
        response = get_html(admin_client, build_html_query("roi"))
        assert response.status_code == 200
        assert b"Period:" in response.content

    def test_roi_empty_data_returns_200(self, admin_client):
        """No job data should still render a valid HTML page."""
        response = get_html(admin_client, build_html_query("roi"))
        assert response.status_code == 200
        assert b"<html" in response.content


# =============================================================================
# Trends HTML report
# =============================================================================


@pytest.mark.unit
@pytest.mark.django_db(transaction=True, reset_sequences=True)
class TestExportHTMLTrends:
    """Verify trends HTML report content."""

    @pytest.fixture(autouse=True)
    def fixed_cost(self):
        with patch(
            "apps.dashboard_reports.models.SubscriptionCost.per_second_subscription_cost",
            return_value=FIXED_PER_SECOND_COST,
        ):
            yield

    def test_trends_contains_report_title(self, job_data, admin_client):
        response = get_html(admin_client, build_html_query("trends"))
        assert response.status_code == 200
        assert b"Trends" in response.content

    def test_trends_contains_date_column_header(self, job_data, admin_client):
        response = get_html(admin_client, build_html_query("trends"))
        assert response.status_code == 200
        assert b"Date" in response.content

    def test_trends_contains_granularity_badge(self, job_data, admin_client):
        response = get_html(admin_client, build_html_query("trends"))
        assert response.status_code == 200
        assert b"Granularity" in response.content

    def test_trends_empty_data_returns_200(self, admin_client):
        response = get_html(admin_client, build_html_query("trends"))
        assert response.status_code == 200
        assert b"<html" in response.content


# =============================================================================
# Validation errors
# =============================================================================


@pytest.mark.unit
@pytest.mark.django_db
class TestExportHTMLValidation:
    """Invalid parameters should still return 400, same as CSV path."""

    def test_invalid_report_type_returns_400(self, admin_client):
        response = get_html(admin_client, {**build_html_query(), "report_type": "bogus"})
        assert response.status_code == 400

    def test_invalid_export_format_returns_400(self, admin_client):
        url = reverse("dashboard_reports:report-export")
        response = admin_client.get(
            url, data={"period": "last_14_days", "tz": "UTC", "report_type": "summary", "export_format": "pdf"}
        )
        assert response.status_code == 400

    def test_missing_period_returns_400(self, admin_client):
        url = reverse("dashboard_reports:report-export")
        response = admin_client.get(url, data={"export_format": "html", "report_type": "summary"})
        assert response.status_code == 400

    def test_pdf_format_rejected(self, admin_client):
        """pdf is no longer a valid format — expect 400."""
        url = reverse("dashboard_reports:report-export")
        response = admin_client.get(
            url, data={"period": "last_14_days", "tz": "UTC", "report_type": "summary", "export_format": "pdf"}
        )
        assert response.status_code == 400
        assert b"csv, html" in response.content


# =============================================================================
# PassthroughRendererHTML
# =============================================================================


@pytest.mark.unit
class TestPassthroughRendererHTML:
    """Verify the HTML renderer has the correct media_type and format."""

    def test_renderer_media_type(self):
        from apps.dashboard_reports.viewsets.dashboard_report import PassthroughRendererHTML

        assert PassthroughRendererHTML.media_type == "text/html"

    def test_renderer_format(self):
        from apps.dashboard_reports.viewsets.dashboard_report import PassthroughRendererHTML

        assert PassthroughRendererHTML.format == "html"

    def test_render_returns_data_as_is(self):
        from apps.dashboard_reports.viewsets.dashboard_report import PassthroughRendererHTML

        renderer = PassthroughRendererHTML()
        data = b"<html></html>"
        assert renderer.render(data) == data
