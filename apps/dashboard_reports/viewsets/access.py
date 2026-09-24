"""Dashboard access discovery endpoint."""

from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.dashboard_reports.awx_queries import fetch_controller_organizations
from apps.dashboard_reports.permissions import get_dashboard_scope
from apps.tasks.task_groups import get_feature_enabled_from_db
from apps.tasks.utils import get_db_connection


class DashboardAccessView(APIView):
    """Report whether a caller has global access or organization-scoped dashboard access."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Get dashboard access scope",
        responses={
            200: inline_serializer(
                name="DashboardAccess",
                fields={
                    "scope": serializers.ChoiceField(choices=["global", "organization"]),
                    "dashboard_enabled": serializers.BooleanField(),
                    "organizations": inline_serializer(
                        name="DashboardAccessibleOrganization",
                        fields={
                            "id": serializers.IntegerField(help_text="AWX organization ID"),
                            "name": serializers.CharField(),
                            "can_edit": serializers.BooleanField(),
                        },
                        many=True,
                    ),
                },
            )
        },
    )
    def get(self, request, *args, **kwargs):
        """Return accessible Controller organization IDs and their edit capability."""
        scope = get_dashboard_scope(request.user)
        dashboard_enabled = get_feature_enabled_from_db("DASHBOARD_COLLECTION", default=True)
        if not scope.global_access and not scope.organizations:
            return Response({"scope": "organization", "dashboard_enabled": dashboard_enabled, "organizations": []})

        can_edit_by_uuid = {org.ansible_id: org.can_edit for org in scope.organizations}
        rows = fetch_controller_organizations(
            get_db_connection("awx"), ansible_ids=None if scope.global_access else scope.ansible_ids
        )
        if not scope.global_access:
            rows = [row for row in rows if row["ansible_id"] in can_edit_by_uuid]
        organizations = [
            {"id": row["id"], "name": row["name"], "can_edit": can_edit_by_uuid.get(row["ansible_id"], False)}
            for row in rows
        ]
        organizations.sort(key=lambda org: (org["name"].casefold(), org["id"]))
        return Response(
            {
                "scope": "global" if scope.global_access else "organization",
                "dashboard_enabled": dashboard_enabled,
                "organizations": organizations,
            }
        )
