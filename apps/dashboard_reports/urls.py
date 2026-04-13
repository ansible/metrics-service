"""URL configuration for dashboard reports API endpoints."""

from ansible_base.lib.routers import AssociationResourceRouter
from django.urls import include, path

from apps.dashboard_reports.viewsets import (
    DashboardReportViewSet,
    FilterSetsViewSet,
    JobTemplatesViewSet,
    LabelsViewSet,
    OrganizationsViewSet,
    ProjectsViewSet,
    SubscriptionCostViewSet,
    TemplateMetadataViewSet,
)

app_name = "dashboard_reports"

router = AssociationResourceRouter()
router.register(r"organizations", OrganizationsViewSet, basename="organizations")
router.register(r"templates", JobTemplatesViewSet, basename="templates")
router.register(r"projects", ProjectsViewSet, basename="projects")
router.register(r"labels", LabelsViewSet, basename="labels")
router.register(r"report", DashboardReportViewSet, basename="report")
router.register(r"subscription_costs", SubscriptionCostViewSet, basename="subscription_costs")
router.register(r"template_metadata", TemplateMetadataViewSet, basename="template_metadata")
router.register(r"filter_sets", FilterSetsViewSet, basename="filter_sets")

urlpatterns = [
    path("api/v1/dashboard_reports/", include(router.urls)),
]
