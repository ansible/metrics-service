import pytest
from django.urls import reverse

from apps.dashboard_reports.urls import router
from apps.dashboard_reports.viewsets import (
    DashboardReportViewSet,
    JobTemplatesViewSet,
    LabelsViewSet,
    OrganizationsViewSet,
    ProjectsViewSet,
)


@pytest.mark.unit
class TestURLConfiguration:
    """Test that all expected ViewSets are registered in the router."""

    @staticmethod
    def is_viewset_registered(viewset):
        """Helper to check if a viewset is registered in the router."""
        return viewset in [reg[1] for reg in router.registry]

    @pytest.mark.parametrize(
        "viewset",
        [
            pytest.param(OrganizationsViewSet, id="organizations_viewset"),
            pytest.param(JobTemplatesViewSet, id="job_templates_viewset"),
            pytest.param(ProjectsViewSet, id="projects_viewset"),
            pytest.param(LabelsViewSet, id="labels_viewset"),
            pytest.param(DashboardReportViewSet, id="dashboard_report_viewset"),
        ],
    )
    def test_viewsets_registered(self, viewset):
        assert self.is_viewset_registered(viewset), f"{viewset.__name__} not registered in router"


@pytest.mark.unit
class TestURLReverse:
    """Test that all expected URL patterns can be reversed correctly."""

    @pytest.mark.parametrize(
        "viewname, endpoint, kwargs",
        [
            pytest.param("v1:organizations-list", "organizations", None, id="organizations_list"),
            pytest.param(
                "v1:organizations-detail", "organizations", {"pk": 1}, id="organizations_detail"
            ),
            pytest.param("v1:templates-list", "templates", None, id="templates_list"),
            pytest.param("v1:templates-detail", "templates", {"pk": 1}, id="templates_detail"),
            pytest.param("v1:projects-list", "projects", None, id="projects_list"),
            pytest.param("v1:projects-detail", "projects", {"pk": 1}, id="projects_detail"),
            pytest.param("v1:labels-list", "labels", None, id="labels_list"),
            pytest.param("v1:labels-detail", "labels", {"pk": 1}, id="labels_detail"),
            pytest.param("v1:report-list", "report", None, id="report_list"),
            pytest.param("v1:report-details", "report", None, id="report_details"),
        ],
    )
    def test_url_reverse(self, viewname, endpoint, kwargs):
        if kwargs is not None:
            url = reverse(viewname, kwargs=kwargs)
            for key, value in kwargs.items():
                assert str(value) in url, f"Expected {key}={value} in URL {url}"
        else:
            url = reverse(viewname)
        assert url is not None
        assert endpoint in url
