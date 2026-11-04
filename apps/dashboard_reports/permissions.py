"""Dashboard organization scope and permission helpers."""

import json
from dataclasses import dataclass
from uuid import UUID

from ansible_base.rbac.evaluations import has_super_permission
from ansible_base.resource_registry.models import Resource
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import BasePermission

from apps.core.models import Organization

# Reuse existing Gateway organization permissions for dashboard capabilities.
VIEW_DASHBOARD = "member_organization"
EDIT_DASHBOARD = "change_organization"


@dataclass(frozen=True)
class DashboardOrganization:
    """An organization the current caller may view, including its stable shared ID."""

    id: int
    name: str
    ansible_id: UUID
    can_edit: bool


@dataclass(frozen=True)
class DashboardScope:
    """Resolved dashboard scope for one caller."""

    global_access: bool
    organizations: tuple[DashboardOrganization, ...]

    @property
    def ansible_ids(self) -> tuple[UUID, ...]:
        return tuple(org.ansible_id for org in self.organizations)


def _organization_resource_map(organizations) -> dict[int, UUID]:
    """Return local Organization PK to shared Resource.ansible_id mappings."""
    object_ids = [str(pk) for pk in organizations.values_list("pk", flat=True)]
    if not object_ids:
        return {}
    content_type = Resource.objects.filter(
        content_type__app_label=Organization._meta.app_label,
        content_type__model=Organization._meta.model_name,
    )
    return {
        int(object_id): ansible_id
        for object_id, ansible_id in content_type.filter(object_id__in=object_ids).values_list(
            "object_id", "ansible_id"
        )
    }


def get_dashboard_scope(user) -> DashboardScope:
    """Resolve global access or organizations where the user is a member or organization admin."""
    if has_super_permission(user, "view"):
        orgs = Organization.objects.all()
        resource_ids = _organization_resource_map(orgs)
        is_admin = has_super_permission(user)
        organizations = tuple(
            DashboardOrganization(org.pk, org.name, resource_ids[org.pk], is_admin)
            for org in orgs
            if org.pk in resource_ids
        )
        return DashboardScope(True, organizations)

    view_orgs = Organization.access_qs(user, VIEW_DASHBOARD)
    edit_orgs = Organization.access_qs(user, EDIT_DASHBOARD)
    editable_ids = set(edit_orgs.values_list("pk", flat=True))
    visible_ids = set(view_orgs.values_list("pk", flat=True)) | editable_ids
    orgs = Organization.objects.filter(pk__in=visible_ids)
    resource_ids = _organization_resource_map(orgs)
    organizations = tuple(
        DashboardOrganization(org.pk, org.name, resource_ids[org.pk], org.pk in editable_ids)
        for org in orgs
        if org.pk in resource_ids
    )
    return DashboardScope(False, organizations)


def is_dashboard_admin(user) -> bool:
    """Return whether the caller has system-wide write permission."""
    return has_super_permission(user)


def filter_set_organization_ids(filters) -> list[int] | None:
    """Return the AWX organization IDs referenced by a saved filter set.

    ``None`` means the filter set has no organization filter, so it spans every
    organization the caller can see. The UI stores filters as a JSON string in
    the ``FilterSet.filters`` JSON field, while tests and other callers may pass
    a dict directly.
    """
    if isinstance(filters, str):
        try:
            filters = json.loads(filters)
        except (TypeError, ValueError):
            return None
    if not isinstance(filters, dict):
        return None

    raw_ids = filters.get("organization", filters.get("organization_id"))
    if raw_ids is None:
        return None
    if not isinstance(raw_ids, (list, tuple)):
        raw_ids = [raw_ids]

    organization_ids = []
    for raw_id in raw_ids:
        try:
            organization_ids.append(int(raw_id))
        except (TypeError, ValueError):
            continue
    return organization_ids


def user_can_save_report(user, filters) -> bool:
    """Return whether the caller may create or update a saved dashboard report.

    Option B semantics:
    - system administrators may save any report;
    - organization admins (``change_organization``) may save reports that stay
      within organizations they can edit;
    - organization members (``member_organization`` only) may not save reports;
    - a report with no organization filter spans every visible organization, so
      it requires edit permission on all of them;
    - view-only organizations must never be included in a saved report.
    """
    if is_dashboard_admin(user):
        return True

    scope = get_dashboard_scope(user)
    if scope.global_access or not scope.organizations:
        return False

    editable_ids = {org.ansible_id for org in scope.organizations if org.can_edit}
    selected_ids = filter_set_organization_ids(filters)

    if selected_ids is None:
        # No organization filter: the report covers every visible organization.
        return len(editable_ids) == len(scope.organizations)
    if not selected_ids:
        return False

    from apps.dashboard_reports.awx_queries import fetch_controller_organizations
    from apps.tasks.utils import get_db_connection

    rows = fetch_controller_organizations(get_db_connection("awx"), ansible_ids=scope.ansible_ids)
    ansible_id_by_awx_id = {row["id"]: row["ansible_id"] for row in rows}
    return all(ansible_id_by_awx_id.get(awx_id) in editable_ids for awx_id in selected_ids)


def scope_jobdata_queryset(user, queryset):
    """Apply the caller's organization boundary to a JobData queryset."""
    scope = get_dashboard_scope(user)
    return queryset if scope.global_access else queryset.filter(organization_ansible_id__in=scope.ansible_ids)


def resolve_selected_organization(
    request, scope: DashboardScope, *, require_edit: bool = False
) -> DashboardOrganization:
    """Resolve an AWX numeric organization ID to an authorized DAB organization."""
    from apps.dashboard_reports.awx_queries import fetch_controller_organizations
    from apps.tasks.utils import get_db_connection

    raw_id = request.query_params.get("organization")
    try:
        awx_id = int(raw_id)
    except (TypeError, ValueError) as exc:
        raise ValidationError({"organization": "Provide a valid AWX organization ID."}) from exc

    selected_rows = fetch_controller_organizations(
        get_db_connection("awx"),
        ansible_ids=None if scope.global_access else scope.ansible_ids,
        organization_id=awx_id,
    )
    if not selected_rows:
        raise NotFound("Organization not found.")
    ansible_id = selected_rows[0]["ansible_id"]
    selected = next((org for org in scope.organizations if org.ansible_id == ansible_id), None)
    if selected is None:
        raise NotFound("Organization not found.")
    if require_edit and not selected.can_edit:
        raise NotFound("Organization not found.")
    return selected


def can_view_dashboard(user) -> bool:
    """Return whether a user can access any dashboard organization or global dashboard data."""
    return has_super_permission(user, "view") or get_dashboard_scope(user).organizations != ()


class DashboardReadPermission(BasePermission):
    """Allow platform dashboard readers and organization members/admins."""

    def has_permission(self, request, view) -> bool:
        return bool(request.user and request.user.is_authenticated and can_view_dashboard(request.user))


def organization_for_ansible_id(ansible_id: UUID) -> Organization | None:
    """Resolve a local Organization from its shared resource UUID."""
    resource = Resource.objects.filter(
        content_type__app_label=Organization._meta.app_label,
        content_type__model=Organization._meta.model_name,
        ansible_id=ansible_id,
    ).first()
    if resource is None:
        return None
    try:
        return Organization.objects.get(pk=int(resource.object_id))
    except (Organization.DoesNotExist, ValueError):
        return None
