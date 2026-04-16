"""Unit tests for DashboardReportViewSet PDF export endpoint (summary, roi, trends)."""

import datetime
import decimal
from unittest.mock import patch
from urllib.parse import urlencode

import pytest
from django.http import HttpResponse
from django.urls import reverse

from apps.dashboard_reports.models import (
    JobData,
    JobStatusChoices,
    TemplateMetadata,
)

FIXED_DAILY_SUBSCRIPTION_COST = decimal.Decimal("161.29")


def get_now() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


def build_pdf_export_query(report_type: str = "summary", days_back: int = 14, **extra) -> dict:
    query = {
        "period": f"last_{days_back}_days",
        "tz": "UTC",
        "report_type": report_type,
        "export_format": "pdf",
    }
    query.update(extra)
    return query


def get_pdf(client, params: dict):
    """GET the export endpoint with params encoded in the query string."""
    url = reverse("dashboard_reports:report-export")
    qs = urlencode(params, doseq=True)
    return client.get(f"{url}?{qs}")


def make_fake_pdf_response(report_type: str) -> HttpResponse:
    """Return a minimal fake PDF HttpResponse for mocking WeasyTemplateResponse."""
    response = HttpResponse(content=b"%PDF-fake", content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="automation-dashboard-{report_type}-2026-04-16.pdf"'
    return response


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
    # Anchor to noon UTC *yesterday* so all timestamps are always in the past
    # and all offsets (minutes=1..5 and days=7,hours=1..2) always land in the
    # same intended day bucket regardless of when the test runs.
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
# Tests — PassthroughRendererPDF
# =============================================================================


@pytest.mark.unit
class TestPassthroughRendererPDF:
    """Tests for the PassthroughRendererPDF class."""

    def test_renderer_media_type(self):
        from apps.dashboard_reports.viewsets.dashboard_report import PassthroughRendererPDF

        assert PassthroughRendererPDF.media_type == "application/pdf"

    def test_renderer_format(self):
        from apps.dashboard_reports.viewsets.dashboard_report import PassthroughRendererPDF

        assert PassthroughRendererPDF.format == "pdf"

    def test_render_returns_data_as_is(self):
        from apps.dashboard_reports.viewsets.dashboard_report import PassthroughRendererPDF

        renderer = PassthroughRendererPDF()
        data = b"%PDF-fake"
        assert renderer.render(data) == data

    def test_render_with_none_data(self):
        from apps.dashboard_reports.viewsets.dashboard_report import PassthroughRendererPDF

        renderer = PassthroughRendererPDF()
        assert renderer.render(None) is None


# =============================================================================
# Tests — export PDF endpoint: general behaviour
# =============================================================================


@pytest.mark.unit
@pytest.mark.django_db
class TestExportPDFEndpointGeneral:
    """Tests for general PDF export endpoint behaviour (routing, headers, errors)."""

    @pytest.fixture(autouse=True)
    def fixed_subscription_cost(self):
        with patch(
            "apps.dashboard_reports.models.SubscriptionCost.daily_subscription_cost",
            return_value=FIXED_DAILY_SUBSCRIPTION_COST,
        ):
            yield

    @pytest.fixture(autouse=True)
    def mock_weasyprint(self):
        """Prevent actual PDF rendering in unit tests."""
        with patch(
            "apps.dashboard_reports.viewsets.dashboard_report.WeasyTemplateResponse",
            side_effect=lambda *a, **kw: make_fake_pdf_response(kw.get("context", {}).get("report_type", "summary")),
        ):
            yield

    def test_pdf_export_missing_period_returns_400(self, admin_client):
        url = reverse("dashboard_reports:report-export")
        qs = urlencode({"export_format": "pdf", "report_type": "summary"})
        response = admin_client.get(f"{url}?{qs}")
        assert response.status_code == 400

    def test_pdf_export_invalid_period_returns_400(self, admin_client):
        response = get_pdf(
            admin_client, {"period": "last_999_days", "tz": "UTC", "report_type": "summary", "export_format": "pdf"}
        )
        assert response.status_code == 400

    def test_pdf_export_invalid_report_type_returns_400(self, admin_client):
        response = get_pdf(
            admin_client, {"period": "last_14_days", "tz": "UTC", "report_type": "invalid_type", "export_format": "pdf"}
        )
        assert response.status_code == 400

    def test_pdf_export_unauthenticated_returns_403(self, api_client):
        response = get_pdf(api_client, build_pdf_export_query("summary"))
        assert response.status_code == 403

    def test_pdf_export_filename_contains_report_type(self, job_data, admin_client):
        for report_type in ("summary", "roi", "trends"):
            response = get_pdf(admin_client, build_pdf_export_query(report_type))
            assert response.status_code == 200
            assert report_type in response["Content-Disposition"]

    def test_pdf_export_filename_ends_with_pdf(self, job_data, admin_client):
        response = get_pdf(admin_client, build_pdf_export_query("summary"))
        assert response.status_code == 200
        assert ".pdf" in response["Content-Disposition"]

    def test_pdf_export_content_disposition_is_attachment(self, job_data, admin_client):
        response = get_pdf(admin_client, build_pdf_export_query("summary"))
        assert response.status_code == 200
        assert "attachment" in response["Content-Disposition"]


# =============================================================================
# Tests — _build_pdf_summary
# =============================================================================


@pytest.mark.unit
@pytest.mark.django_db(transaction=True, reset_sequences=True)
class TestBuildPDFSummary:
    """Tests for _build_pdf_summary context construction."""

    @pytest.fixture(autouse=True)
    def fixed_subscription_cost(self):
        with patch(
            "apps.dashboard_reports.models.SubscriptionCost.daily_subscription_cost",
            return_value=FIXED_DAILY_SUBSCRIPTION_COST,
        ):
            yield

    def test_summary_context_contains_table_data(self, job_data, admin_client):
        captured = {}

        def capture_response(*args, **kwargs):
            captured.update(kwargs.get("context", {}))
            return make_fake_pdf_response("summary")

        with patch(
            "apps.dashboard_reports.viewsets.dashboard_report.WeasyTemplateResponse", side_effect=capture_response
        ):
            response = get_pdf(admin_client, build_pdf_export_query("summary"))

        assert response.status_code == 200
        assert "table_data" in captured
        assert len(captured["table_data"]) == 2

    def test_summary_context_contains_details(self, job_data, admin_client):
        captured = {}

        def capture_response(*args, **kwargs):
            captured.update(kwargs.get("context", {}))
            return make_fake_pdf_response("summary")

        with patch(
            "apps.dashboard_reports.viewsets.dashboard_report.WeasyTemplateResponse", side_effect=capture_response
        ):
            get_pdf(admin_client, build_pdf_export_query("summary"))

        assert "details" in captured
        assert captured["details"]["total_number_of_job_runs"] == 4

    def test_summary_context_contains_date_range(self, job_data, admin_client):
        captured = {}

        def capture_response(*args, **kwargs):
            captured.update(kwargs.get("context", {}))
            return make_fake_pdf_response("summary")

        with patch(
            "apps.dashboard_reports.viewsets.dashboard_report.WeasyTemplateResponse", side_effect=capture_response
        ):
            get_pdf(admin_client, build_pdf_export_query("summary"))

        assert "start_date" in captured
        assert "end_date" in captured

    def test_summary_context_enable_template_creation_time(self, job_data, admin_client):
        captured = {}

        def capture_response(*args, **kwargs):
            captured.update(kwargs.get("context", {}))
            return make_fake_pdf_response("summary")

        with patch(
            "apps.dashboard_reports.viewsets.dashboard_report.WeasyTemplateResponse", side_effect=capture_response
        ):
            get_pdf(admin_client, build_pdf_export_query("summary"))

        assert "enable_template_creation_time" in captured

    def test_summary_uses_correct_template(self, job_data, admin_client):
        captured = {}

        def capture_response(*args, **kwargs):
            captured["template"] = kwargs.get("template")
            return make_fake_pdf_response("summary")

        with patch(
            "apps.dashboard_reports.viewsets.dashboard_report.WeasyTemplateResponse", side_effect=capture_response
        ):
            get_pdf(admin_client, build_pdf_export_query("summary"))

        assert captured["template"] == "dashboard_reports/report_summary.html"

    def test_summary_period_filter_limits_table_data(self, job_data, admin_client):
        """last_7_days should include only Template A in table_data."""
        captured = {}

        def capture_response(*args, **kwargs):
            captured.update(kwargs.get("context", {}))
            return make_fake_pdf_response("summary")

        with patch(
            "apps.dashboard_reports.viewsets.dashboard_report.WeasyTemplateResponse", side_effect=capture_response
        ):
            get_pdf(admin_client, build_pdf_export_query("summary", days_back=7))

        assert len(captured["table_data"]) == 1
        assert captured["table_data"][0]["template_name"] == "Template A"


# =============================================================================
# Tests — _build_pdf_roi
# =============================================================================


@pytest.mark.unit
@pytest.mark.django_db(transaction=True, reset_sequences=True)
class TestBuildPDFROI:
    """Tests for _build_pdf_roi context construction."""

    @pytest.fixture(autouse=True)
    def fixed_subscription_cost(self):
        with patch(
            "apps.dashboard_reports.models.SubscriptionCost.daily_subscription_cost",
            return_value=FIXED_DAILY_SUBSCRIPTION_COST,
        ):
            yield

    def _post_roi(self, admin_client, capture: dict, **extra):
        def capture_response(*args, **kwargs):
            capture.update(kwargs.get("context", {}))
            return make_fake_pdf_response("roi")

        with patch(
            "apps.dashboard_reports.viewsets.dashboard_report.WeasyTemplateResponse", side_effect=capture_response
        ):
            return get_pdf(admin_client, build_pdf_export_query("roi", **extra))

    def test_roi_uses_correct_template(self, job_data, admin_client):
        captured = {}

        def capture_response(*args, **kwargs):
            captured["template"] = kwargs.get("template")
            return make_fake_pdf_response("roi")

        with patch(
            "apps.dashboard_reports.viewsets.dashboard_report.WeasyTemplateResponse", side_effect=capture_response
        ):
            get_pdf(admin_client, build_pdf_export_query("roi"))

        assert captured["template"] == "dashboard_reports/report_roi.html"

    def test_roi_context_contains_all_fields(self, job_data, admin_client):
        captured = {}
        self._post_roi(admin_client, captured)
        for field in (
            "cost_savings",
            "time_saved_hours",
            "automation_cost",
            "manual_cost_equivalent",
            "roi_percentage",
            "automation_value",
        ):
            assert field in captured, f"Missing field: {field}"

    def test_roi_automation_value_equals_manual_cost_plus_savings(self, job_data, admin_client):
        captured = {}
        self._post_roi(admin_client, captured)
        assert abs(
            decimal.Decimal(str(captured["automation_value"]))
            - (
                decimal.Decimal(str(captured["manual_cost_equivalent"]))
                + decimal.Decimal(str(captured["cost_savings"]))
            )
        ) < decimal.Decimal("0.01")

    def test_roi_percentage_calculation(self, job_data, admin_client):
        """roi_percentage = (savings / automated_costs) * 100."""
        captured = {}
        self._post_roi(admin_client, captured)
        automation_cost = decimal.Decimal(str(captured["automation_cost"]))
        cost_savings = decimal.Decimal(str(captured["cost_savings"]))
        roi_percentage = decimal.Decimal(str(captured["roi_percentage"]))
        if automation_cost > 0:
            expected = round((cost_savings / automation_cost) * 100, 2)
            assert abs(roi_percentage - expected) < decimal.Decimal("0.1")

    def test_roi_empty_data_returns_zeros(self, admin_client):
        captured = {}
        self._post_roi(admin_client, captured)
        for field in ("cost_savings", "automation_cost", "manual_cost_equivalent", "automation_value"):
            assert float(captured[field]) == 0.0, f"Expected 0 for {field} with no data"

    def test_roi_organization_filter_affects_context(self, job_data, admin_client):
        all_captured: dict = {}
        org_captured: dict = {}
        self._post_roi(admin_client, all_captured)
        self._post_roi(admin_client, org_captured, organization=[1])
        # Template B (org=2) has high automation-creation-time costs that make its savings negative,
        # so the all-org total is lower than org=1 (Template A) alone.
        assert float(org_captured["cost_savings"]) > float(all_captured["cost_savings"])

    def test_roi_context_contains_date_range(self, job_data, admin_client):
        captured = {}
        self._post_roi(admin_client, captured)
        assert "start_date" in captured
        assert "end_date" in captured


# =============================================================================
# Tests — _build_pdf_trends
# =============================================================================


@pytest.mark.unit
@pytest.mark.django_db(transaction=True, reset_sequences=True)
class TestBuildPDFTrends:
    """Tests for _build_pdf_trends context construction."""

    @pytest.fixture(autouse=True)
    def fixed_subscription_cost(self):
        with patch(
            "apps.dashboard_reports.models.SubscriptionCost.daily_subscription_cost",
            return_value=FIXED_DAILY_SUBSCRIPTION_COST,
        ):
            yield

    def _post_trends(self, admin_client, capture: dict, **extra):
        def capture_response(*args, **kwargs):
            capture.update(kwargs.get("context", {}))
            return make_fake_pdf_response("trends")

        with patch(
            "apps.dashboard_reports.viewsets.dashboard_report.WeasyTemplateResponse", side_effect=capture_response
        ):
            return get_pdf(admin_client, build_pdf_export_query("trends", **extra))

    def test_trends_uses_correct_template(self, job_data, admin_client):
        captured = {}

        def capture_response(*args, **kwargs):
            captured["template"] = kwargs.get("template")
            return make_fake_pdf_response("trends")

        with patch(
            "apps.dashboard_reports.viewsets.dashboard_report.WeasyTemplateResponse", side_effect=capture_response
        ):
            get_pdf(admin_client, build_pdf_export_query("trends"))

        assert captured["template"] == "dashboard_reports/report_trends.html"

    def test_trends_context_contains_rows(self, job_data, admin_client):
        captured = {}
        self._post_trends(admin_client, captured)
        assert "rows" in captured
        assert len(captured["rows"]) >= 1

    def test_trends_context_contains_granularity(self, job_data, admin_client):
        captured = {}
        self._post_trends(admin_client, captured)
        assert "granularity" in captured
        assert captured["granularity"] in ("hour", "day", "week", "month", "year")

    def test_trends_rows_have_required_fields(self, job_data, admin_client):
        captured = {}
        self._post_trends(admin_client, captured)
        for row in captured["rows"]:
            for field in ("date", "runs", "successful_runs", "failed_runs", "total_elapsed_str", "total_hosts"):
                assert field in row, f"Missing field: {field}"

    def test_trends_total_runs_matches_job_count(self, job_data, admin_client):
        captured = {}
        self._post_trends(admin_client, captured)
        total = sum(row["runs"] for row in captured["rows"])
        assert total == 4

    def test_trends_successful_plus_failed_equals_total(self, job_data, admin_client):
        captured = {}
        self._post_trends(admin_client, captured)
        for row in captured["rows"]:
            assert row["successful_runs"] + row["failed_runs"] == row["runs"]

    def test_trends_rows_ordered_by_date_ascending(self, job_data, admin_client):
        captured = {}
        self._post_trends(admin_client, captured)
        dates = [row["date"] for row in captured["rows"]]
        assert dates == sorted(dates)

    def test_trends_day_granularity_produces_two_buckets(self, job_data, admin_client):
        """last_14_days → kind=day → jobs on two distinct days → 2 buckets."""
        captured = {}
        self._post_trends(admin_client, captured, days_back=14)
        assert len(captured["rows"]) == 2

    def test_trends_organization_filter(self, job_data, admin_client):
        """Filtering by org=1 should return only Template A buckets (2 runs total)."""
        captured = {}
        self._post_trends(admin_client, captured, organization=[1])
        total = sum(row["runs"] for row in captured["rows"])
        assert total == 2

    def test_trends_context_contains_date_range(self, job_data, admin_client):
        captured = {}
        self._post_trends(admin_client, captured)
        assert "start_date" in captured
        assert "end_date" in captured

    def test_trends_context_filters_populated_when_filter_active(self, job_data, admin_client):
        """Passing organization filter should populate the filters key in context."""
        captured = {}
        self._post_trends(admin_client, captured, organization=[1])
        assert "filters" in captured
        assert "organization" in captured["filters"]
        assert captured["filters"]["organization"]["name"] == "Organization"
        assert "1" in captured["filters"]["organization"]["values"]


# =============================================================================
# Tests — _build_filter_labels
# =============================================================================


@pytest.mark.unit
@pytest.mark.django_db
class TestBuildFilterLabels:
    """Tests for _build_filter_labels via captured PDF context."""

    @pytest.fixture(autouse=True)
    def fixed_subscription_cost(self):
        with patch(
            "apps.dashboard_reports.models.SubscriptionCost.daily_subscription_cost",
            return_value=FIXED_DAILY_SUBSCRIPTION_COST,
        ):
            yield

    def _capture_context(self, admin_client, report_type: str = "summary", **extra_params) -> dict:
        captured = {}

        def capture_response(*args, **kwargs):
            captured.update(kwargs.get("context", {}))
            return make_fake_pdf_response(report_type)

        with patch(
            "apps.dashboard_reports.viewsets.dashboard_report.WeasyTemplateResponse", side_effect=capture_response
        ):
            get_pdf(admin_client, build_pdf_export_query(report_type, **extra_params))
        return captured

    def test_filter_labels_empty_when_no_filters(self, admin_client):
        captured = self._capture_context(admin_client)
        assert captured["filters"] == {}

    def test_filter_labels_single_organization(self, admin_client):
        captured = self._capture_context(admin_client, organization=[1])
        assert "organization" in captured["filters"]
        assert captured["filters"]["organization"]["name"] == "Organization"
        assert captured["filters"]["organization"]["values"] == "1"

    def test_filter_labels_multiple_organizations(self, admin_client):
        captured = self._capture_context(admin_client, organization=[1, 2])
        assert "organization" in captured["filters"]
        assert captured["filters"]["organization"]["values"] == "1, 2"

    def test_filter_labels_multiple_filter_types(self, admin_client):
        captured = self._capture_context(admin_client, organization=[1], template=[2], project=[3])
        assert "organization" in captured["filters"]
        assert "template" in captured["filters"]
        assert "project" in captured["filters"]

    def test_filter_labels_unknown_params_not_included(self, admin_client):
        """Query params outside the filter_map should not appear in filters."""
        captured = self._capture_context(admin_client)
        for key in captured["filters"]:
            assert key in ("organization", "template", "project", "label")


# =============================================================================
# Tests — PDF summary: additional context keys
# =============================================================================


@pytest.mark.unit
@pytest.mark.django_db(transaction=True, reset_sequences=True)
class TestBuildPDFSummaryExtra:
    """Additional context-key tests for _build_pdf_summary."""

    @pytest.fixture(autouse=True)
    def fixed_subscription_cost(self):
        with patch(
            "apps.dashboard_reports.models.SubscriptionCost.daily_subscription_cost",
            return_value=FIXED_DAILY_SUBSCRIPTION_COST,
        ):
            yield

    def _capture_summary(self, admin_client, **extra) -> tuple[dict, object]:
        captured = {}

        def capture_response(*args, **kwargs):
            captured.update(kwargs.get("context", {}))
            return make_fake_pdf_response("summary")

        with patch(
            "apps.dashboard_reports.viewsets.dashboard_report.WeasyTemplateResponse", side_effect=capture_response
        ):
            response = get_pdf(admin_client, build_pdf_export_query("summary", **extra))
        return captured, response

    def test_summary_context_contains_currency(self, job_data, admin_client):
        captured, _ = self._capture_summary(admin_client)
        assert captured.get("currency") == "$"

    def test_summary_context_filters_populated_when_filter_active(self, job_data, admin_client):
        captured, _ = self._capture_summary(admin_client, organization=[1])
        assert "filters" in captured
        assert "organization" in captured["filters"]
        assert captured["filters"]["organization"]["name"] == "Organization"

    def test_summary_max_pdf_templates_limits_table_data(self, admin_client):
        """Create more than MAX_PDF_JOB_TEMPLATES templates; table_data must be capped at 50."""
        limit = 50
        templates = TemplateMetadata.objects.bulk_create(
            [
                TemplateMetadata(
                    template_id=i,
                    template_name=f"Template {i}",
                    time_taken_manually_execute_minutes=10,
                    time_taken_create_automation_minutes=2,
                )
                for i in range(1, limit + 2)  # 51 templates
            ]
        )
        now = (get_now() - datetime.timedelta(days=1)).replace(hour=12, minute=0, second=0, microsecond=0)
        JobData.objects.bulk_create(
            [
                JobData(
                    job_id=i,
                    template_id=t.template_id,
                    template_name=t.template_name,
                    project_id=1,
                    project_name="Project",
                    organization_id=1,
                    status=JobStatusChoices.SUCCESSFUL,
                    started=now - datetime.timedelta(minutes=5),
                    finished=now - datetime.timedelta(minutes=1),
                    elapsed=60,
                    num_hosts=1,
                    template_metadata=t,
                )
                for i, t in enumerate(templates, start=1)
            ]
        )
        captured, response = self._capture_summary(admin_client)
        assert response.status_code == 200
        assert len(captured["table_data"]) == limit


# =============================================================================
# Tests — PDF ROI: additional context keys
# =============================================================================


@pytest.mark.unit
@pytest.mark.django_db(transaction=True, reset_sequences=True)
class TestBuildPDFROIExtra:
    """Additional context-key tests for _build_pdf_roi."""

    @pytest.fixture(autouse=True)
    def fixed_subscription_cost(self):
        with patch(
            "apps.dashboard_reports.models.SubscriptionCost.daily_subscription_cost",
            return_value=FIXED_DAILY_SUBSCRIPTION_COST,
        ):
            yield

    def _capture_roi(self, admin_client, **extra) -> dict:
        captured = {}

        def capture_response(*args, **kwargs):
            captured.update(kwargs.get("context", {}))
            return make_fake_pdf_response("roi")

        with patch(
            "apps.dashboard_reports.viewsets.dashboard_report.WeasyTemplateResponse", side_effect=capture_response
        ):
            get_pdf(admin_client, build_pdf_export_query("roi", **extra))
        return captured

    def test_roi_context_contains_currency(self, job_data, admin_client):
        captured = self._capture_roi(admin_client)
        assert captured.get("currency") == "$"

    def test_roi_context_filters_populated_when_filter_active(self, job_data, admin_client):
        captured = self._capture_roi(admin_client, organization=[1])
        assert "filters" in captured
        assert "organization" in captured["filters"]

    def test_roi_period_filter_affects_context(self, job_data, admin_client):
        """last_7_days (only Template A) vs last_14_days (both templates) should differ."""
        captured_7 = self._capture_roi(admin_client, days_back=7)
        captured_14 = self._capture_roi(admin_client, days_back=14)
        assert float(captured_7["cost_savings"]) != float(captured_14["cost_savings"])


# =============================================================================
# Tests — _export_csv / _export_pdf method dispatch
# =============================================================================


@pytest.mark.unit
@pytest.mark.django_db
class TestExportMethodDispatch:
    """Tests for _export_csv and _export_pdf method-check logic."""

    @pytest.fixture(autouse=True)
    def fixed_subscription_cost(self):
        with patch(
            "apps.dashboard_reports.models.SubscriptionCost.daily_subscription_cost",
            return_value=FIXED_DAILY_SUBSCRIPTION_COST,
        ):
            yield

    @pytest.fixture(autouse=True)
    def mock_weasyprint(self):
        with patch(
            "apps.dashboard_reports.viewsets.dashboard_report.WeasyTemplateResponse",
            side_effect=lambda *a, **kw: make_fake_pdf_response(kw.get("context", {}).get("report_type", "summary")),
        ):
            yield

    def test_csv_export_via_post_returns_405(self, admin_client):
        """CSV export only supports GET — POST should return 405."""
        url = reverse("dashboard_reports:report-export")
        qs = urlencode({"period": "last_14_days", "tz": "UTC", "report_type": "summary", "export_format": "csv"})
        response = admin_client.post(f"{url}?{qs}")
        assert response.status_code == 405

    def test_csv_post_405_detail_message(self, admin_client):
        url = reverse("dashboard_reports:report-export")
        qs = urlencode({"period": "last_14_days", "tz": "UTC", "report_type": "roi", "export_format": "csv"})
        response = admin_client.post(f"{url}?{qs}")
        assert response.status_code == 405
        assert "GET" in response["Allow"]  # DRF sets the Allow header to list permitted methods


# =============================================================================
# Tests — _build_filter_labels: label filter (raw IDs fallback)
# =============================================================================


@pytest.mark.unit
@pytest.mark.django_db
class TestBuildFilterLabelsLabel:
    """Tests for the label param in _build_filter_labels (raw ID fallback path)."""

    @pytest.fixture(autouse=True)
    def fixed_subscription_cost(self):
        with patch(
            "apps.dashboard_reports.models.SubscriptionCost.daily_subscription_cost",
            return_value=FIXED_DAILY_SUBSCRIPTION_COST,
        ):
            yield

    def _capture_filters(self, admin_client, **extra_params) -> dict:
        captured = {}

        def capture_response(*args, **kwargs):
            captured.update(kwargs.get("context", {}))
            return make_fake_pdf_response("summary")

        with patch(
            "apps.dashboard_reports.viewsets.dashboard_report.WeasyTemplateResponse",
            side_effect=capture_response,
        ):
            get_pdf(admin_client, build_pdf_export_query("summary", **extra_params))
        return captured.get("filters", {})

    def test_label_filter_shows_raw_ids(self, admin_client):
        """Labels have no name lookup — raw IDs should appear as the badge value."""
        filters = self._capture_filters(admin_client, label=[42])
        assert "label" in filters
        assert filters["label"]["name"] == "Label"
        assert "42" in filters["label"]["values"]

    def test_label_filter_not_included_when_absent(self, admin_client):
        """No label param → label key should not appear in filters."""
        filters = self._capture_filters(admin_client)
        assert "label" not in filters


# =============================================================================
# Tests — _build_pdf_trends: kind=None fallback
# =============================================================================


@pytest.mark.unit
@pytest.mark.django_db
class TestBuildPDFTrendsKindFallback:
    """Tests the kind='day' fallback in _build_pdf_trends when _get_date_range_and_kind returns None."""

    @pytest.fixture(autouse=True)
    def fixed_subscription_cost(self):
        with patch(
            "apps.dashboard_reports.models.SubscriptionCost.daily_subscription_cost",
            return_value=FIXED_DAILY_SUBSCRIPTION_COST,
        ):
            yield

    def test_trends_uses_day_fallback_when_kind_is_none(self, admin_client):
        """When _get_date_range_and_kind returns None for kind, _build_pdf_trends should fall back to 'day'."""
        captured = {}

        def capture_response(*args, **kwargs):
            captured.update(kwargs.get("context", {}))
            return make_fake_pdf_response("trends")

        with (
            patch(
                "apps.dashboard_reports.viewsets.dashboard_report.WeasyTemplateResponse",
                side_effect=capture_response,
            ),
            patch(
                "apps.dashboard_reports.viewsets.dashboard_report.DashboardReportViewSet._get_date_range_and_kind",
                return_value=(None, None, None),
            ),
        ):
            response = get_pdf(admin_client, build_pdf_export_query("trends"))

        assert response.status_code == 200
        assert captured.get("granularity") == "day"
