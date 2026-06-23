from urllib.parse import urlencode

import pytest
from django.urls import reverse
from rest_framework import status

from apps.dashboard_reports.models import AWXJobTemplate, AWXLabel, AWXOrganization, AWXProject


@pytest.fixture
def org(db):
    return AWXOrganization.objects.create(org_id=1, name="Default")


@pytest.fixture
def org2(db):
    return AWXOrganization.objects.create(org_id=2, name="Operations")


@pytest.fixture
def template(db):
    return AWXJobTemplate.objects.create(template_id=10, name="Deploy App")


@pytest.fixture
def project(db):
    return AWXProject.objects.create(project_id=5, name="ansible-playbooks")


@pytest.fixture
def label(db):
    return AWXLabel.objects.create(label_id=42, name="production")


@pytest.fixture
def label2(db):
    return AWXLabel.objects.create(label_id=43, name="staging")


@pytest.mark.unit
@pytest.mark.django_db
class TestOrganizationsViewSet:
    def test_list_returns_cached_orgs(self, admin_client, org, org2):
        response = admin_client.get(reverse("v1:organizations-list"))
        assert response.status_code == status.HTTP_200_OK
        names = [r["name"] for r in response.data["results"]]
        assert "Default" in names
        assert "Operations" in names

    def test_list_empty_when_no_cache(self, admin_client):
        response = admin_client.get(reverse("v1:organizations-list"))
        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] == 0
        assert response.data["results"] == []

    def test_list_search_filters_by_name(self, admin_client, org, org2):
        url = reverse("v1:organizations-list") + "?" + urlencode({"search": "Oper"})
        response = admin_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] == 1
        assert response.data["results"][0]["name"] == "Operations"

    def test_list_search_no_results(self, admin_client, org):
        url = reverse("v1:organizations-list") + "?" + urlencode({"search": "XYZ999"})
        response = admin_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] == 0

    def test_retrieve_by_awx_id(self, admin_client, org):
        response = admin_client.get(reverse("v1:organizations-detail", kwargs={"pk": 1}))
        assert response.status_code == status.HTTP_200_OK
        assert response.data == {"id": 1, "name": "Default"}

    def test_retrieve_returns_404_for_unknown_id(self, admin_client):
        response = admin_client.get(reverse("v1:organizations-detail", kwargs={"pk": 9999}))
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_retrieve_returns_404_for_invalid_id(self, admin_client):
        response = admin_client.get(reverse("v1:organizations-detail", kwargs={"pk": 0}))
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_list_results_contain_id_and_name(self, admin_client, org):
        response = admin_client.get(reverse("v1:organizations-list"))
        result = response.data["results"][0]
        assert "id" in result
        assert "name" in result


@pytest.mark.unit
@pytest.mark.django_db
class TestJobTemplatesViewSet:
    def test_list_returns_cached_templates(self, admin_client, template):
        response = admin_client.get(reverse("v1:templates-list"))
        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] == 1
        assert response.data["results"][0] == {"id": 10, "name": "Deploy App"}

    def test_list_empty_when_no_cache(self, admin_client):
        response = admin_client.get(reverse("v1:templates-list"))
        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] == 0

    def test_retrieve_by_awx_id(self, admin_client, template):
        response = admin_client.get(reverse("v1:templates-detail", kwargs={"pk": 10}))
        assert response.status_code == status.HTTP_200_OK
        assert response.data == {"id": 10, "name": "Deploy App"}

    def test_retrieve_returns_404_for_unknown_id(self, admin_client):
        response = admin_client.get(reverse("v1:templates-detail", kwargs={"pk": 9999}))
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_search_filters_templates(self, admin_client, template):
        url = reverse("v1:templates-list") + "?" + urlencode({"search": "Deploy"})
        response = admin_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] == 1

        url_no_match = reverse("v1:templates-list") + "?" + urlencode({"search": "XYZ"})
        response_no_match = admin_client.get(url_no_match)
        assert response_no_match.data["count"] == 0


@pytest.mark.unit
@pytest.mark.django_db
class TestProjectsViewSet:
    def test_list_returns_cached_projects(self, admin_client, project):
        response = admin_client.get(reverse("v1:projects-list"))
        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] == 1
        assert response.data["results"][0] == {"id": 5, "name": "ansible-playbooks"}

    def test_list_empty_when_no_cache(self, admin_client):
        response = admin_client.get(reverse("v1:projects-list"))
        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] == 0

    def test_retrieve_by_awx_id(self, admin_client, project):
        response = admin_client.get(reverse("v1:projects-detail", kwargs={"pk": 5}))
        assert response.status_code == status.HTTP_200_OK
        assert response.data == {"id": 5, "name": "ansible-playbooks"}

    def test_retrieve_returns_404_for_unknown_id(self, admin_client):
        response = admin_client.get(reverse("v1:projects-detail", kwargs={"pk": 9999}))
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_search_filters_projects(self, admin_client, project):
        url = reverse("v1:projects-list") + "?" + urlencode({"search": "ansible"})
        response = admin_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] == 1


@pytest.mark.unit
@pytest.mark.django_db
class TestLabelsViewSet:
    def test_list_returns_cached_labels(self, admin_client, label, label2):
        response = admin_client.get(reverse("v1:labels-list"))
        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] == 2
        names = [r["name"] for r in response.data["results"]]
        assert "production" in names
        assert "staging" in names

    def test_list_empty_when_no_cache(self, admin_client):
        response = admin_client.get(reverse("v1:labels-list"))
        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] == 0

    def test_retrieve_by_awx_id(self, admin_client, label):
        response = admin_client.get(reverse("v1:labels-detail", kwargs={"pk": 42}))
        assert response.status_code == status.HTTP_200_OK
        assert response.data == {"id": 42, "name": "production"}

    def test_retrieve_returns_404_for_unknown_id(self, admin_client):
        response = admin_client.get(reverse("v1:labels-detail", kwargs={"pk": 9999}))
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_search_filters_labels(self, admin_client, label, label2):
        url = reverse("v1:labels-list") + "?" + urlencode({"search": "prod"})
        response = admin_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] == 1
        assert response.data["results"][0]["name"] == "production"


@pytest.mark.unit
@pytest.mark.django_db
@pytest.mark.parametrize(
    "endpoint, method, pk",
    [
        pytest.param("v1:organizations-list", "post", None, id="organizations_list_post"),
        pytest.param("v1:templates-list", "post", None, id="templates_list_post"),
        pytest.param("v1:projects-list", "post", None, id="projects_list_post"),
        pytest.param("v1:labels-list", "post", None, id="labels_list_post"),
        pytest.param("v1:organizations-detail", "put", 1, id="organizations_detail_put"),
        pytest.param("v1:templates-detail", "put", 1, id="templates_detail_put"),
        pytest.param("v1:projects-detail", "put", 1, id="projects_detail_put"),
        pytest.param("v1:labels-detail", "put", 1, id="labels_detail_put"),
        pytest.param("v1:organizations-detail", "patch", 1, id="organizations_detail_patch"),
        pytest.param("v1:templates-detail", "patch", 1, id="templates_detail_patch"),
        pytest.param("v1:projects-detail", "patch", 1, id="projects_detail_patch"),
        pytest.param("v1:labels-detail", "patch", 1, id="labels_detail_patch"),
        pytest.param("v1:organizations-detail", "delete", 1, id="organizations_detail_delete"),
        pytest.param("v1:templates-detail", "delete", 1, id="templates_detail_delete"),
        pytest.param("v1:projects-detail", "delete", 1, id="projects_detail_delete"),
        pytest.param("v1:labels-detail", "delete", 1, id="labels_detail_delete"),
    ],
)
def test_http_method_not_allowed(endpoint, method, pk, admin_client):
    url = reverse(endpoint, kwargs={"pk": pk}) if pk else reverse(endpoint)
    request_method = getattr(admin_client, method)
    response = request_method(url, data={}) if method != "delete" else request_method(url)
    assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED
