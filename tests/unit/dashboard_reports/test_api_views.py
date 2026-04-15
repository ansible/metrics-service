from unittest.mock import MagicMock, patch
from urllib.parse import urlencode

import pytest
from django.test import override_settings
from django.urls import reverse
from rest_framework import status


@pytest.mark.unit
@pytest.mark.django_db
@patch("apps.dashboard_reports.viewsets.filter_options.get_db_connection", return_value=MagicMock())
class TestCommonViewSets:
    """
    Tests for
        - OrganizationsViewSet endpoints,
        - JobTemplatesViewSet endpoints,
        - ProjectsViewSet endpoints,
        - LabelsViewSet endpoints.
    """

    @pytest.mark.parametrize(
        "endpoint, viewset_name, kwargs, mocked_data, expected_status, expected_data",
        [
            # OrganizationsViewSet tests
            pytest.param(
                "v1:organizations-list",
                "OrganizationsViewSet",
                None,
                [{"id": 1, "name": "Org 1"}, {"id": 2, "name": "Org 2"}],
                status.HTTP_200_OK,
                {"count": 2, "results": [{"id": 1, "name": "Org 1"}, {"id": 2, "name": "Org 2"}]},
                id="organizations_list_with_data",
            ),
            pytest.param(
                "v1:organizations-list",
                "OrganizationsViewSet",
                None,
                [],
                status.HTTP_200_OK,
                {"count": 0, "results": []},
                id="organizations_list_empty",
            ),
            pytest.param(
                "v1:organizations-list",
                "OrganizationsViewSet",
                {"search": "Nonexistent Org"},
                [],
                status.HTTP_200_OK,
                {"count": 0, "results": []},
                id="organizations_list_search_no_results",
            ),
            pytest.param(
                "v1:organizations-detail",
                "OrganizationsViewSet",
                {"pk": 1},
                [{"id": 1, "name": "Org 1"}],
                status.HTTP_200_OK,
                {"id": 1, "name": "Org 1"},
                id="organizations_detail_found",
            ),
            pytest.param(
                "v1:organizations-detail",
                "OrganizationsViewSet",
                {"pk": 1},
                [],
                status.HTTP_404_NOT_FOUND,
                None,
                id="organizations_detail_not_found",
            ),
            # JobTemplatesViewSet tests
            pytest.param(
                "v1:templates-list",
                "JobTemplatesViewSet",
                None,
                [{"id": 1, "name": "Template A"}, {"id": 2, "name": "Template B"}],
                status.HTTP_200_OK,
                {"count": 2, "results": [{"id": 1, "name": "Template A"}, {"id": 2, "name": "Template B"}]},
                id="templates_list_with_data",
            ),
            pytest.param(
                "v1:templates-list",
                "JobTemplatesViewSet",
                None,
                [],
                status.HTTP_200_OK,
                {"count": 0, "results": []},
                id="templates_list_empty",
            ),
            pytest.param(
                "v1:templates-list",
                "JobTemplatesViewSet",
                {"search": "Nonexistent Template"},
                [],
                status.HTTP_200_OK,
                {"count": 0, "results": []},
                id="templates_list_search_no_results",
            ),
            pytest.param(
                "v1:templates-detail",
                "JobTemplatesViewSet",
                {"pk": 1},
                [{"id": 1, "name": "Template A"}],
                status.HTTP_200_OK,
                {"id": 1, "name": "Template A"},
                id="templates_detail_found",
            ),
            pytest.param(
                "v1:templates-detail",
                "JobTemplatesViewSet",
                {"pk": 1},
                [],
                status.HTTP_404_NOT_FOUND,
                None,
                id="templates_detail_not_found",
            ),
            # ProjectsViewSet tests
            pytest.param(
                "v1:projects-list",
                "ProjectsViewSet",
                None,
                [{"id": 1, "name": "Project X"}, {"id": 2, "name": "Project Y"}],
                status.HTTP_200_OK,
                {"count": 2, "results": [{"id": 1, "name": "Project X"}, {"id": 2, "name": "Project Y"}]},
                id="projects_list_with_data",
            ),
            pytest.param(
                "v1:projects-list",
                "ProjectsViewSet",
                None,
                [],
                status.HTTP_200_OK,
                {"count": 0, "results": []},
                id="projects_list_empty",
            ),
            pytest.param(
                "v1:projects-list",
                "ProjectsViewSet",
                {"search": "Nonexistent Project"},
                [],
                status.HTTP_200_OK,
                {"count": 0, "results": []},
                id="projects_list_search_no_results",
            ),
            pytest.param(
                "v1:projects-detail",
                "ProjectsViewSet",
                {"pk": 1},
                [{"id": 1, "name": "Project X"}],
                status.HTTP_200_OK,
                {"id": 1, "name": "Project X"},
                id="projects_detail_found",
            ),
            pytest.param(
                "v1:projects-detail",
                "ProjectsViewSet",
                {"pk": 1},
                [],
                status.HTTP_404_NOT_FOUND,
                None,
                id="projects_detail_not_found",
            ),
            # LabelsViewSet tests
            pytest.param(
                "v1:labels-list",
                "LabelsViewSet",
                None,
                [{"id": 1, "name": "Label 1"}, {"id": 2, "name": "Label 2"}],
                status.HTTP_200_OK,
                {"count": 2, "results": [{"id": 1, "name": "Label 1"}, {"id": 2, "name": "Label 2"}]},
                id="labels_list_with_data",
            ),
            pytest.param(
                "v1:labels-list",
                "LabelsViewSet",
                None,
                [],
                status.HTTP_200_OK,
                {"count": 0, "results": []},
                id="labels_list_empty",
            ),
            pytest.param(
                "v1:labels-list",
                "LabelsViewSet",
                {"search": "Nonexistent Label"},
                [],
                status.HTTP_200_OK,
                {"count": 0, "results": []},
                id="labels_list_search_no_results",
            ),
            pytest.param(
                "v1:labels-detail",
                "LabelsViewSet",
                {"pk": 1},
                [{"id": 1, "name": "Label 1"}],
                status.HTTP_200_OK,
                {"id": 1, "name": "Label 1"},
                id="labels_detail_found",
            ),
            pytest.param(
                "v1:labels-detail",
                "LabelsViewSet",
                {"pk": 1},
                [],
                status.HTTP_404_NOT_FOUND,
                None,
                id="labels_detail_not_found",
            ),
        ],
    )
    def test_views_response(
        self, _, endpoint, viewset_name, kwargs, mocked_data, expected_status, expected_data, admin_client
    ):
        # _ is the mock from @patch decorator; unused because we patch awx_query_function directly in the test
        # awx_query_function now returns (items, total_count) — wrap mocked_data accordingly.
        mocked_return = (mocked_data, len(mocked_data))
        with (
            override_settings(DEBUG=True),
            patch(
                f"apps.dashboard_reports.viewsets.{viewset_name}.awx_query_function", return_value=mocked_return
            ) as mock_awx_query_function,
        ):
            pk = kwargs.get("pk") if kwargs else None
            search = kwargs.get("search") if kwargs else None
            if pk is not None:
                url = reverse(endpoint, kwargs={"pk": pk})
            elif search is not None:
                url = reverse(endpoint) + "?" + urlencode({"search": search})
            else:
                url = reverse(endpoint)
            client = admin_client
            response = client.get(url)
            assert response.status_code == expected_status
            if expected_data is not None:
                data = response.data
                for key, value in expected_data.items():
                    assert key in data, f"Expected key '{key}' in response data"
                    assert data[key] == value, f"Expected '{key}' to be {value}, got {data[key]}"
            if search is not None:
                assert mock_awx_query_function.call_args[1]["search_str"] == search
                # List path must forward pagination params to the query function
                assert "limit" in mock_awx_query_function.call_args[1]
                assert "offset" in mock_awx_query_function.call_args[1]
            elif pk is not None:
                assert mock_awx_query_function.call_args[1]["pk"] == pk
            else:
                assert mock_awx_query_function.call_count == 1
                # List path must forward pagination params to the query function
                assert "limit" in mock_awx_query_function.call_args[1]
                assert "offset" in mock_awx_query_function.call_args[1]

    @pytest.mark.parametrize(
        "endpoint, method, pk",
        [
            # POST not allowed on list endpoints
            pytest.param("v1:organizations-list", "post", None, id="organizations_list_post"),
            pytest.param("v1:templates-list", "post", None, id="templates_list_post"),
            pytest.param("v1:projects-list", "post", None, id="projects_list_post"),
            pytest.param("v1:labels-list", "post", None, id="labels_list_post"),
            # PUT not allowed on detail endpoints
            pytest.param("v1:organizations-detail", "put", 1, id="organizations_detail_put"),
            pytest.param("v1:templates-detail", "put", 1, id="templates_detail_put"),
            pytest.param("v1:projects-detail", "put", 1, id="projects_detail_put"),
            pytest.param("v1:labels-detail", "put", 1, id="labels_detail_put"),
            # PATCH not allowed on detail endpoints
            pytest.param("v1:organizations-detail", "patch", 1, id="organizations_detail_patch"),
            pytest.param("v1:templates-detail", "patch", 1, id="templates_detail_patch"),
            pytest.param("v1:projects-detail", "patch", 1, id="projects_detail_patch"),
            pytest.param("v1:labels-detail", "patch", 1, id="labels_detail_patch"),
            # DELETE not allowed on detail endpoints
            pytest.param("v1:organizations-detail", "delete", 1, id="organizations_detail_delete"),
            pytest.param("v1:templates-detail", "delete", 1, id="templates_detail_delete"),
            pytest.param("v1:projects-detail", "delete", 1, id="projects_detail_delete"),
            pytest.param("v1:labels-detail", "delete", 1, id="labels_detail_delete"),
        ],
    )
    def test_http_method_not_allowed(self, _, endpoint, method, pk, admin_client):
        """Test that POST, PUT, PATCH, DELETE requests are not allowed on respective endpoints."""
        # _ is the mock from @patch decorator; unused as we only test HTTP method rejection
        url = reverse(endpoint, kwargs={"pk": pk}) if pk else reverse(endpoint)
        client = admin_client
        request_method = getattr(client, method)
        response = request_method(url, data={}) if method != "delete" else request_method(url)
        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED
