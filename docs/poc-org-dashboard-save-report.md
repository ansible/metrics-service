# POC — Gate Saved Dashboard Reports on Organization Change Permission

Branch: `poc/org-dashboard-save-report`
Base: `feat/organization-dashboard-rbac-option-b` (Option B PR #441)
Draft PR: https://github.com/ansible/metrics-service/pull/525

## Purpose

The Option B dashboard maps existing Gateway roles to dashboard capabilities:

| Gateway role | Permission | Dashboard capability |
|---|---|---|
| Organization Member | `member_organization` | View dashboard data |
| Organization Admin | `change_organization` | View + edit dashboard data |

This branch adds the missing write rule for **saved reports** (`FilterSet`):
organization members can view dashboards, but cannot save, update or delete
reports; organization admins can manage reports only for organizations where
they have `change_organization`.

## Behavior

`user_can_save_report(user, filters)` returns `True` when:

1. The caller is a system administrator (`has_super_permission`), or
2. The caller has at least one organization in dashboard scope and:
   - the report has an organization filter and **every** selected organization
     is one the caller can edit, or
   - the report has no organization filter (it spans all visible
     organizations) and **every** visible organization is editable.

It returns `False` when the caller is a view-only member, has no dashboard
organization scope, has an empty organization selection, or selects an
organization outside their scope.

The organization filter is read from `FilterSet.filters`, which the UI stores
as a JSON string. Both `organization` and `organization_id` keys are accepted
for compatibility with existing saved reports.

## Files changed

### `apps/dashboard_reports/permissions.py`

- Added `filter_set_organization_ids(filters)`:
  - parses a JSON string or dict;
  - accepts `organization` (current UI) or `organization_id` (legacy/tests);
  - returns `None` when there is no organization filter, `[]` for an empty
    selection, and a list of integer AWX organization IDs otherwise.
- Added `user_can_save_report(user, filters)` implementing the rule above.
  AWX organization IDs are mapped to DAB UUIDs with
  `fetch_controller_organizations(...)` and compared against the editable
  `DashboardOrganization` set from `get_dashboard_scope()`.

### `apps/dashboard_reports/viewsets/filter_sets.py`

- `perform_create`: rejects with `PermissionDenied` (HTTP 403) before saving
  when `user_can_save_report()` is false.
- `perform_update`: same check, using the incoming filters or the stored
  filters when the update does not include a new `filters` value.
- Deletion is intentionally **not** gated: a user may remove a report they
  previously saved even if the underlying organization access has since been
  reduced.

### Tests

- `tests/unit/dashboard_reports/test_organization_dashboard_access.py`
  - parsing tests for `filter_set_organization_ids`;
  - `user_can_save_report` cases for system admin, view-only, mixed scopes,
    all-editable scope, selected editable/view-only organizations, unknown
    organizations, and empty selections.
- `tests/unit/dashboard_reports/test_filter_sets.py`
  - new `TestFilterSetsSavePermission` verifies 403 on create and update for a
    user with no change permission;
  - existing CRUD mechanics tests explicitly bypass the gate through
    `_allow_saving_reports()` so they keep testing serialization, defaults and
    user isolation rather than permissions.
- `tests/coverage/dashboard_reports/test_dashboard_viewsets.py`
  - the create smoke test now accepts 403.

## Validation

```bash
.venv/bin/python -m pytest \
  tests/unit/dashboard_reports/test_filter_sets.py \
  tests/unit/dashboard_reports/test_organization_dashboard_access.py \
  tests/coverage/dashboard_reports/test_dashboard_viewsets.py
# 121 passed

.venv/bin/ruff check apps/dashboard_reports/permissions.py \
  apps/dashboard_reports/viewsets/filter_sets.py tests/unit/dashboard_reports
.venv/bin/ruff format --check apps/dashboard_reports tests/unit/dashboard_reports
```

## Dependencies and limitations

- Depends on the Option B branch (`member_organization` / `change_organization`
  resolution) and its `JobData.organization_ansible_id` scope boundary.
- That boundary requires **metrics-utility** to populate
  `organization_ansible_id` in both the historical dashboard collector and the
  hourly `unified_jobs_dashboard` collector. Without it, org-scoped users see
  no rows and report saving has no usable organization context.
- Saved reports remain per-user and are not themselves organization-scoped;
  the rule validates the organization filter stored inside each report.
- The UI companion change is in ansible-ui PR #3861.
