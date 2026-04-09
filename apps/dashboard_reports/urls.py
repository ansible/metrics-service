from ansible_base.lib.routers import AssociationResourceRouter
from django.urls import include, path

from apps.dashboard_reports.viewsets import (
    DashboardReportViewSet,
    JobTemplatesViewSet,
    LabelsViewSet,
    OrganizationsViewSet,
    ProjectsViewSet,
    TemplateMetadataViewSet,
)

app_name = "dashboard_reports"

router = AssociationResourceRouter()
router.register(r"organizations", OrganizationsViewSet, basename="organizations")
router.register(r"templates", JobTemplatesViewSet, basename="templates")
router.register(r"projects", ProjectsViewSet, basename="projects")
router.register(r"labels", LabelsViewSet, basename="labels")
router.register(r"report", DashboardReportViewSet, basename="report")

# TemplateMetadataViewSet doesn't fit the standard router pattern, so we define its URL separately
#   * standard router pattern example: /api/v1/dashboard_reports/templates/metadata/{id}/
#   * what we want is: /api/v1/dashboard_reports/templates/{id}/metadata/
metadata_view = TemplateMetadataViewSet.as_view(
    {
        "get": "retrieve",
        "put": "update",
        "patch": "partial_update",
        "delete": "destroy",
    }
)

urlpatterns = [
    # Dashboard report endpoints at /api/v1/
    path("api/v1/dashboard_reports/templates/<int:pk>/metadata/", metadata_view, name="template-metadata"),
    path("api/v1/dashboard_reports/", include(router.urls)),
]
