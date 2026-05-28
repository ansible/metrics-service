"""URL configuration for BI connector analytics endpoints.

Mounts at /api/v1/bi/metrics/ via apps/urls.py (included under the metrics/ namespace).

Endpoints:
    GET /api/v1/bi/metrics/modules/         - per-module compute hours and task runs
    GET /api/v1/bi/metrics/organizations/   - per-org job and task totals
    GET /api/v1/bi/metrics/compute-hours/   - aggregate automation compute hours summary
"""

from django.urls import path

from .analytics_views import ComputeHoursView, ModuleStatsView, OrganizationStatsView

urlpatterns = [
    path("modules/", ModuleStatsView.as_view(), name="module-stats"),
    path("organizations/", OrganizationStatsView.as_view(), name="organization-stats"),
    path("compute-hours/", ComputeHoursView.as_view(), name="compute-hours"),
]
