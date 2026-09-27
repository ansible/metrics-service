"""Organization dashboard authorization and private settings tests."""

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import UUID

import pytest
from django.test import RequestFactory
from rest_framework.exceptions import NotFound
from rest_framework.request import Request
from rest_framework.test import APIClient

from apps.dashboard_reports.permissions import DashboardOrganization, DashboardScope

ORG_A_UUID = UUID("11111111-1111-1111-1111-111111111111")
ORG_B_UUID = UUID("22222222-2222-2222-2222-222222222222")


@pytest.mark.unit
def test_dashboard_read_permission_accepts_viewer_editor_and_denies_no_role():
    from apps.dashboard_reports.permissions import DashboardReadPermission

    user = SimpleNamespace(is_authenticated=True)
    request = SimpleNamespace(user=user)
    permission = DashboardReadPermission()
    organization = DashboardOrganization(1, "Org A", ORG_A_UUID, False)
    editor = DashboardOrganization(1, "Org A", ORG_A_UUID, True)

    with (
        patch("apps.dashboard_reports.permissions.has_super_permission", return_value=False),
        patch(
            "apps.dashboard_reports.permissions.get_dashboard_scope",
            return_value=DashboardScope(False, (organization,)),
        ),
    ):
        assert permission.has_permission(request, None) is True
    with (
        patch("apps.dashboard_reports.permissions.has_super_permission", return_value=False),
        patch("apps.dashboard_reports.permissions.get_dashboard_scope", return_value=DashboardScope(False, (editor,))),
    ):
        assert permission.has_permission(request, None) is True
    with (
        patch("apps.dashboard_reports.permissions.has_super_permission", return_value=False),
        patch("apps.dashboard_reports.permissions.get_dashboard_scope", return_value=DashboardScope(False, ())),
    ):
        assert permission.has_permission(request, None) is False
    with patch(
        "apps.dashboard_reports.permissions.has_super_permission",
        side_effect=lambda requested_user, codename=None: codename == "view",
    ):
        assert permission.has_permission(request, None) is True


@pytest.mark.unit
def test_selected_organization_write_requires_editor_role():
    from apps.dashboard_reports.permissions import resolve_selected_organization

    organization = DashboardOrganization(1, "Org A", ORG_A_UUID, False)
    scope = DashboardScope(False, (organization,))
    request = SimpleNamespace(query_params={"organization": "501"})
    with (
        patch(
            "apps.dashboard_reports.awx_queries.fetch_controller_organizations",
            return_value=[{"id": 501, "name": "Org A", "ansible_id": ORG_A_UUID}],
        ),
        patch("apps.tasks.utils.get_db_connection", return_value=MagicMock()),
        pytest.raises(NotFound),
    ):
        resolve_selected_organization(request, scope, require_edit=True)


@pytest.mark.unit
def test_zero_monthly_cost_override_is_not_replaced_by_global_cost():
    from apps.dashboard_reports.models import SubscriptionCost

    cost = SubscriptionCost(monthly_subscription_cost=Decimal("900.00"), engineer_avg_hourly_rate=Decimal("60.00"))
    start = datetime(2026, 1, 1, tzinfo=UTC)
    end = datetime(2026, 1, 10, tzinfo=UTC)
    with patch("apps.dashboard_reports.models.JobData.objects.filter") as jobs_filter:
        queryset = MagicMock()
        queryset.filter.return_value = queryset
        queryset.aggregate.return_value = {"total_seconds": Decimal("100")}
        jobs_filter.return_value = queryset
        result = cost.per_second_subscription_cost(
            start, end, organization_ansible_id=ORG_A_UUID, monthly_subscription_cost=Decimal("0.00")
        )

    assert result == Decimal("0E-10")
    jobs_filter.assert_called_once()


@pytest.mark.unit
@pytest.mark.django_db
def test_report_queryset_intersects_forged_org_filters_with_uuid_scope():
    from apps.dashboard_reports.models import JobData
    from apps.dashboard_reports.viewsets.dashboard_report import CustomReportFilter, DashboardReportViewSet

    request = Request(
        RequestFactory().get(
            "/api/v1/dashboard_reports/report/",
            {"period": "last_30_days", "organization": "999", "or__organization": "888"},
        )
    )
    request._user = SimpleNamespace(is_authenticated=True)
    view = DashboardReportViewSet()
    view.request = request
    view.kwargs = {}
    view.filter_backends = [CustomReportFilter]
    scope = DashboardScope(False, (DashboardOrganization(1, "Org A", ORG_A_UUID, False),))

    with patch("apps.dashboard_reports.permissions.get_dashboard_scope", return_value=scope):
        queryset = view._filter_raw_jobdata_queryset(JobData.objects.all())

    sql = str(queryset.query)
    assert "organization_ansible_id" in sql
    assert str(ORG_A_UUID) in sql
    assert "organization_id" in sql
    assert "999" in sql
    assert "888" in sql


@pytest.mark.unit
@pytest.mark.django_db
def test_access_endpoint_returns_only_resolved_authorized_organizations(user):
    client = APIClient()
    client.force_authenticate(user=user)
    scope = DashboardScope(False, (DashboardOrganization(1, "Org A", ORG_A_UUID, True),))
    controller_orgs = [
        {"id": 501, "name": "Org A", "ansible_id": ORG_A_UUID},
        {"id": 502, "name": "Org B", "ansible_id": ORG_B_UUID},
    ]
    db_connection = MagicMock()
    with (
        patch("apps.dashboard_reports.viewsets.access.get_dashboard_scope", return_value=scope),
        patch("apps.dashboard_reports.viewsets.access.get_feature_enabled_from_db", return_value=True),
        patch("apps.dashboard_reports.viewsets.access.get_db_connection", return_value=db_connection),
        patch(
            "apps.dashboard_reports.viewsets.access.fetch_controller_organizations", return_value=controller_orgs
        ) as fetch,
    ):
        response = client.get("/api/v1/dashboard_reports/access/")

    assert response.status_code == 200
    assert response.data == {
        "scope": "organization",
        "dashboard_enabled": True,
        "organizations": [{"id": 501, "name": "Org A", "can_edit": True}],
    }
    fetch.assert_called_once_with(db_connection, ansible_ids=scope.ansible_ids)


@pytest.mark.unit
@pytest.mark.django_db
def test_subscription_cost_override_is_private_per_user_and_organization():
    from django.contrib.auth import get_user_model

    from apps.core.models import Organization
    from apps.dashboard_reports.models import OrganizationDashboardSettings, SubscriptionCost

    user_model = get_user_model()
    editor = user_model.objects.create_user(username="dashboard-editor")
    other_user = user_model.objects.create_user(username="dashboard-viewer")
    org_a = Organization.objects.create(name="Org A")
    org_b = Organization.objects.create(name="Org B")
    global_cost = SubscriptionCost.get()
    selected = {
        "501": DashboardOrganization(org_a.id, org_a.name, ORG_A_UUID, True),
        "502": DashboardOrganization(org_b.id, org_b.name, ORG_B_UUID, True),
    }

    def resolve_org(request, scope, *, require_edit=False):
        org = selected[request.query_params["organization"]]
        if require_edit and not org.can_edit:
            raise NotFound("Organization not found.")
        return org

    with (
        patch(
            "apps.dashboard_reports.viewsets.subscription_cost.DashboardReadPermission.has_permission",
            return_value=True,
        ),
        patch(
            "apps.dashboard_reports.viewsets.subscription_cost.get_dashboard_scope",
            return_value=DashboardScope(False, tuple(selected.values())),
        ),
        patch(
            "apps.dashboard_reports.viewsets.subscription_cost.resolve_selected_organization", side_effect=resolve_org
        ),
    ):
        editor_client = APIClient()
        editor_client.force_authenticate(user=editor)
        response = editor_client.patch(
            "/api/v1/dashboard_reports/subscription_costs/1/?organization=501",
            {"monthly_subscription_cost": "1234.50"},
            format="json",
        )
        assert response.status_code == 200

        other_client = APIClient()
        other_client.force_authenticate(user=other_user)
        other_response = other_client.get("/api/v1/dashboard_reports/subscription_costs/?organization=501")
        second_org_response = editor_client.get("/api/v1/dashboard_reports/subscription_costs/?organization=502")

    assert OrganizationDashboardSettings.objects.get(
        user=editor, organization=org_a
    ).monthly_subscription_cost == Decimal("1234.50")
    assert Decimal(str(other_response.data[0]["monthly_subscription_cost"])) == global_cost.monthly_subscription_cost
    assert (
        Decimal(str(second_org_response.data[0]["monthly_subscription_cost"])) == global_cost.monthly_subscription_cost
    )


@pytest.mark.unit
@pytest.mark.django_db
def test_template_estimate_override_is_private_per_user_and_organization():
    from django.contrib.auth import get_user_model

    from apps.core.models import Organization
    from apps.dashboard_reports.models import JobData, OrganizationTemplateMetadataOverride, TemplateMetadata

    user_model = get_user_model()
    editor = user_model.objects.create_user(username="template-editor")
    other_user = user_model.objects.create_user(username="template-viewer")
    org_a = Organization.objects.create(name="Org A")
    org_b = Organization.objects.create(name="Org B")
    template = TemplateMetadata.objects.create(
        template_id=17,
        template_name="Deploy",
        time_taken_manually_execute_minutes=60,
        time_taken_create_automation_minutes=20,
    )
    for job_id, org_id, org_uuid in ((1, 501, ORG_A_UUID), (2, 502, ORG_B_UUID)):
        JobData.objects.create(
            job_id=job_id,
            template_name="Deploy",
            template_id=17,
            organization_id=org_id,
            organization_ansible_id=org_uuid,
            organization_name="Org A" if org_id == 501 else "Org B",
            status="successful",
            elapsed=Decimal("5.0"),
            template_metadata=template,
        )
    selected = {
        "501": DashboardOrganization(org_a.id, org_a.name, ORG_A_UUID, True),
        "502": DashboardOrganization(org_b.id, org_b.name, ORG_B_UUID, True),
    }

    def resolve_org(request, scope, *, require_edit=False):
        org = selected[request.query_params["organization"]]
        if require_edit and not org.can_edit:
            raise NotFound("Organization not found.")
        return org

    with (
        patch(
            "apps.dashboard_reports.viewsets.template_metadata.DashboardReadPermission.has_permission",
            return_value=True,
        ),
        patch(
            "apps.dashboard_reports.viewsets.template_metadata.get_dashboard_scope",
            return_value=DashboardScope(False, tuple(selected.values())),
        ),
        patch(
            "apps.dashboard_reports.viewsets.template_metadata.resolve_selected_organization", side_effect=resolve_org
        ),
    ):
        editor_client = APIClient()
        editor_client.force_authenticate(user=editor)
        response = editor_client.patch(
            f"/api/v1/dashboard_reports/template_metadata/{template.pk}/?organization=501",
            {"time_taken_manually_execute_minutes": 12},
            format="json",
        )
        assert response.status_code == 200, response.data

        other_client = APIClient()
        other_client.force_authenticate(user=other_user)
        other_response = other_client.get(
            f"/api/v1/dashboard_reports/template_metadata/{template.pk}/?organization=501"
        )
        second_org_response = editor_client.get(
            f"/api/v1/dashboard_reports/template_metadata/{template.pk}/?organization=502"
        )

    assert (
        OrganizationTemplateMetadataOverride.objects.get(
            user=editor, organization=org_a, template_id=17
        ).time_taken_manually_execute_minutes
        == 12
    )
    assert other_response.data["time_taken_manually_execute_minutes"] == 60
    assert second_org_response.data["time_taken_manually_execute_minutes"] == 60


@pytest.mark.unit
@pytest.mark.django_db
def test_viewer_cannot_write_subscription_or_template_overrides():
    from django.contrib.auth import get_user_model

    from apps.core.models import Organization
    from apps.dashboard_reports.models import (
        JobData,
        OrganizationDashboardSettings,
        OrganizationTemplateMetadataOverride,
        TemplateMetadata,
    )

    viewer = get_user_model().objects.create_user(username="dashboard-viewer-only")
    organization = Organization.objects.create(name="Read Only Org")
    template = TemplateMetadata.objects.create(template_id=23, template_name="Read Only Template")
    JobData.objects.create(
        job_id=23,
        template_name="Read Only Template",
        template_id=23,
        organization_id=623,
        organization_ansible_id=ORG_A_UUID,
        organization_name="Read Only Org",
        status="successful",
        elapsed=Decimal("5.0"),
        template_metadata=template,
    )
    scope = DashboardScope(False, (DashboardOrganization(organization.id, organization.name, ORG_A_UUID, False),))
    db_connection = MagicMock()
    controller_org = [{"id": 623, "name": organization.name, "ansible_id": ORG_A_UUID}]
    client = APIClient()
    client.force_authenticate(user=viewer)

    with (
        patch(
            "apps.dashboard_reports.viewsets.subscription_cost.DashboardReadPermission.has_permission",
            return_value=True,
        ),
        patch(
            "apps.dashboard_reports.viewsets.template_metadata.DashboardReadPermission.has_permission",
            return_value=True,
        ),
        patch("apps.dashboard_reports.viewsets.subscription_cost.get_dashboard_scope", return_value=scope),
        patch("apps.dashboard_reports.viewsets.template_metadata.get_dashboard_scope", return_value=scope),
        patch("apps.dashboard_reports.awx_queries.fetch_controller_organizations", return_value=controller_org),
        patch("apps.tasks.utils.get_db_connection", return_value=db_connection),
    ):
        cost_response = client.patch(
            "/api/v1/dashboard_reports/subscription_costs/1/?organization=623",
            {"monthly_subscription_cost": "100.00"},
            format="json",
        )
        template_response = client.patch(
            f"/api/v1/dashboard_reports/template_metadata/{template.pk}/?organization=623",
            {"time_taken_manually_execute_minutes": 10},
            format="json",
        )

    assert cost_response.status_code == 404
    assert template_response.status_code == 404
    assert not OrganizationDashboardSettings.objects.filter(user=viewer, organization=organization).exists()
    assert not OrganizationTemplateMetadataOverride.objects.filter(
        user=viewer, organization=organization, template_id=23
    ).exists()


@pytest.mark.unit
def test_leaderboard_direct_streak_query_is_scoped_to_org_uuid():
    from apps.dashboard_reports.viewsets import dashboard_leaderboards as leaderboards

    captured = {}
    scoped_queryset = MagicMock()
    scoped_queryset.order_by.return_value.values_list.return_value = ["successful", "failed", "successful"]

    def apply_org_scope(user, queryset):
        captured["sql"] = str(queryset.filter(organization_ansible_id=ORG_A_UUID).query)
        return scoped_queryset

    with patch.object(leaderboards, "scope_jobdata_queryset", side_effect=apply_org_scope):
        streak = leaderboards._longest_successful_run_streak(
            12,
            leaderboards.datetime(2026, 1, 1, tzinfo=leaderboards.UTC),
            leaderboards.datetime(2026, 1, 30, tzinfo=leaderboards.UTC),
            user=object(),
        )

    assert streak == 1
    assert "organization_ansible_id" in captured["sql"]
    assert str(ORG_A_UUID) in captured["sql"]
