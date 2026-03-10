import datetime

import pytest
import pytz
from django.urls import reverse
from rest_framework.test import APIClient

from apps.dashboard_reports.models import (
    JobData,
    JobHostSummary,
    JobLabel,
    JobStatusChoices,
    SubscriptionCost,
    TemplateMetadata,
)

# =============================================================================
# Helper functions for building test queries
# =============================================================================


def get_now() -> datetime.datetime:
    """Get current datetime with UTC timezone."""
    return datetime.datetime.now().astimezone(pytz.UTC)


def build_date_query(days_back: int = 10, days_forward: int = 1, hours_forward: int = 0, **extra_filters) -> dict:
    """
    Build a query dict with date range and optional filters.

    Args:
        days_back: Number of days before now for start_date
        days_forward: Number of days after now for end_date
        hours_forward: Number of hours after now for end_date (alternative to days_forward)
        **extra_filters: Additional query parameters (organization, template, project, label)

    Returns:
        Query dict ready to use with API client
    """
    now = get_now()
    query = {
        "start_date": (now - datetime.timedelta(days=days_back)).isoformat(),
        "end_date": (now + datetime.timedelta(days=days_forward, hours=hours_forward)).isoformat(),
    }
    query.update(extra_filters)
    return query


def build_filtered_query(**filters) -> dict:
    """Build query with full date range (10 days back, 1 day forward) and optional filters."""
    return build_date_query(days_back=10, days_forward=1, **filters)


def build_recent_query(**filters) -> dict:
    """Build query for recent data (last 24 hours)."""
    return build_date_query(days_back=1, days_forward=0, hours_forward=1, **filters)


# =============================================================================
# Fixtures for test data setup
# =============================================================================


@pytest.fixture
def template_metadata():
    """Create template metadata for Template A and Template B."""
    templates = [
        TemplateMetadata(
            template_id=1,
            template_name="Template A",
            time_taken_manually_execute_minutes=240,
            time_taken_create_automation_minutes=40,
        ),
        TemplateMetadata(
            template_id=2,
            template_name="Template B",
            time_taken_manually_execute_minutes=360,
            time_taken_create_automation_minutes=60,
        ),
    ]
    return TemplateMetadata.objects.bulk_create(templates)


@pytest.fixture
def job_data(template_metadata):
    """
    Fixture for JobData test data.

    job_id 1 and 2: Template A, organization_id=1, project_id=1, labels 1 and 2, finished=now
    job_id 3 and 4: Template B, organization_id=2, project_id=2, no labels, finished=5 days ago

    All filters (date, organization, template, project, labels) return job_id 1 and 2.
    """
    now = get_now()

    # Job data configuration: (job_id, template_idx, org, project, status, time_offset, elapsed, num_hosts, user_id, username)
    job_configs = [
        # job_id 1: Template A, org=1, project=1, successful, now
        (1, 0, 1, "Project A", JobStatusChoices.SUCCESSFUL, datetime.timedelta(minutes=5), 60, 10, 1, "test_user"),
        # job_id 2: Template A, org=1, project=1, failed, now
        (2, 0, 1, "Project A", JobStatusChoices.FAILED, datetime.timedelta(minutes=1), 5, 10, 1, "test_user"),
        # job_id 3: Template B, org=2, project=2, failed, 5 days ago
        (3, 1, 2, "Project B", JobStatusChoices.FAILED, datetime.timedelta(days=5, hours=1), 50, 1, 2, "other_user"),
        # job_id 4: Template B, org=2, project=2, successful, 5 days ago
        (
            4,
            1,
            2,
            "Project B",
            JobStatusChoices.SUCCESSFUL,
            datetime.timedelta(days=5, hours=2),
            300,
            1,
            2,
            "other_user",
        ),
    ]

    jobs = []
    for job_id, tmpl_idx, org_id, proj_name, status, offset, elapsed, hosts, user_id, username in job_configs:
        tmpl = template_metadata[tmpl_idx]
        jobs.append(
            JobData(
                job_id=job_id,
                template_name=tmpl.template_name,
                template_id=tmpl.template_id,
                project_id=org_id,  # Using org_id as project_id for simplicity
                project_name=proj_name,
                organization_id=org_id,
                status=status,
                started=now - offset - datetime.timedelta(minutes=10),
                finished=now - offset,
                elapsed=elapsed,
                num_hosts=hosts,
                launched_by_id=user_id,
                launched_by_username=username,
                template_metadata=tmpl,
            )
        )

    created_jobs = JobData.objects.bulk_create(jobs)

    # Labels only for job_id 1 and 2 (first two jobs)
    labels = [
        JobLabel(job_data=created_jobs[0], label_id=1),
        JobLabel(job_data=created_jobs[0], label_id=2),
        JobLabel(job_data=created_jobs[1], label_id=1),
        JobLabel(job_data=created_jobs[1], label_id=2),
    ]
    JobLabel.objects.bulk_create(labels)

    # Host summaries for job_id 1 and 2
    summaries = [
        JobHostSummary(host_summary_id=1, job_data=created_jobs[0], host_name="host1", host_id=1),
        JobHostSummary(host_summary_id=2, job_data=created_jobs[0], host_name="host2", host_id=2),
        JobHostSummary(host_summary_id=3, job_data=created_jobs[1], host_name="host1", host_id=1),
        JobHostSummary(host_summary_id=4, job_data=created_jobs[1], host_name="host3", host_id=3),
    ]
    JobHostSummary.objects.bulk_create(summaries)

    return created_jobs


# =============================================================================
# Expected data constants for Template A (job_id 1 and 2)
# =============================================================================
# Calculations (with default SubscriptionCost: cost_employee_per_minute=1.0, include_template_creation_time=True):
# - job_id 1: elapsed=60, num_hosts=10, status=successful
# - job_id 2: elapsed=5, num_hosts=10, status=failed
# - Total: runs=2, successful=1, failed=1, elapsed=65, num_hosts=20
# - automated_costs = (40 * 1.0) + (65 * ~0.00187) = 40.12
# - manual_costs = 20 * 240 * 1.0 = 4800.00
# - time_savings = 288000 - 65 - 2400 = 285535 sec

EXPECTED_TEMPLATE_A_DATA = {
    "template_name": "Template A",
    "template_metadata_id": 1,
    "time_taken_manually_execute_minutes": 240,
    "time_taken_create_automation_minutes": 40,
    "runs": 2,
    "successful_runs": 1,
    "failed_runs": 1,
    "elapsed": "65.00",
    "elapsed_str": "1min 5sec",
    "automated_costs": "40.12",
    "manual_costs": "4800.00",
    "time_savings": "285535.00",
    "time_savings_str": "79h 18min 55sec",
    "savings": "4759.88",
}

# =============================================================================
# Expected data constants for Template B (job_id 3 and 4)
# =============================================================================
# - job_id 3: elapsed=50, num_hosts=1, status=failed
# - job_id 4: elapsed=300, num_hosts=1, status=successful
# - Total: runs=2, successful=1, failed=1, elapsed=350, num_hosts=2

EXPECTED_TEMPLATE_B_DATA = {
    "template_name": "Template B",
    "template_metadata_id": 2,
    "time_taken_manually_execute_minutes": 360,
    "time_taken_create_automation_minutes": 60,
    "runs": 2,
    "successful_runs": 1,
    "failed_runs": 1,
    "elapsed": "350.00",
    "elapsed_str": "5min 50sec",
    "automated_costs": "60.65",
    "manual_costs": "720.00",
    "time_savings": "39250.00",
    "time_savings_str": "10h 54min 10sec",
    "savings": "659.35",
}

# =============================================================================
# Expected data for details endpoint (job_id 1 and 2)
# =============================================================================

EXPECTED_DETAILS_JOB_1_AND_2 = {
    "total_number_of_job_runs": 2,
    "total_number_of_successful_jobs": 1,
    "total_number_of_failed_jobs": 1,
    "total_number_of_host_job_runs": 20,
    "total_number_of_unique_hosts": 3,
    "total_hours_of_automation": 0.02,
    "cost_of_automated_execution": 40.12,
    "cost_of_manual_automation": 4800.0,
    "total_saving": 4759.88,
    "total_time_saving": 79.32,
    "top_users": [
        {"id": 1, "user_name": "test_user", "execution_count": 2},
    ],
    "top_projects": [
        {"id": 1, "project_name": "Project A", "execution_count": 2},
    ],
}

# =============================================================================
# Expected data for all jobs (unfiltered)
# =============================================================================

EXPECTED_DETAILS_ALL_JOBS = {
    "total_number_of_job_runs": 4,
    "total_number_of_successful_jobs": 2,
    "total_number_of_failed_jobs": 2,
    "total_number_of_host_job_runs": 22,
    "total_number_of_unique_hosts": 3,
    "total_hours_of_automation": 0.12,
    "cost_of_automated_execution": 100.77,
    "cost_of_manual_automation": 5520.0,
    "total_saving": 5419.23,
    "total_time_saving": 90.22,
    "top_users": [
        {"id": 1, "user_name": "test_user", "execution_count": 2},
        {"id": 2, "user_name": "other_user", "execution_count": 2},
    ],
    "top_projects": [
        {"id": 1, "project_name": "Project A", "execution_count": 2},
        {"id": 2, "project_name": "Project B", "execution_count": 2},
    ],
}

# =============================================================================
# Test cases for report view
# =============================================================================

TEST_REPORT_VIEW_CASES = [
    # 1. Unfiltered - returns all data
    pytest.param(
        build_filtered_query(),
        2,
        [EXPECTED_TEMPLATE_A_DATA, EXPECTED_TEMPLATE_B_DATA],
        id="unfiltered_all_data",
    ),
    # 2. Filtered by date - last 24 hours returns job_id 1 and 2
    pytest.param(
        build_recent_query(),
        1,
        [EXPECTED_TEMPLATE_A_DATA],
        id="filtered_by_date",
    ),
    # 3. Filtered by organization
    pytest.param(
        build_filtered_query(organization=[1]),
        1,
        [EXPECTED_TEMPLATE_A_DATA],
        id="filtered_by_organization",
    ),
    # 4. Filtered by template_id
    pytest.param(
        build_filtered_query(template=[1]),
        1,
        [EXPECTED_TEMPLATE_A_DATA],
        id="filtered_by_template",
    ),
    # 5. Filtered by project
    pytest.param(
        build_filtered_query(project=[1]),
        1,
        [EXPECTED_TEMPLATE_A_DATA],
        id="filtered_by_project",
    ),
    # 6. Filtered by labels
    pytest.param(
        build_filtered_query(label=[1]),
        1,
        [EXPECTED_TEMPLATE_A_DATA],
        id="filtered_by_labels",
    ),
]

# =============================================================================
# Test cases for report view details
# =============================================================================

TEST_REPORT_VIEW_DETAIL_CASES = [
    # 1. Unfiltered - returns all data (4 jobs)
    pytest.param(
        build_filtered_query(),
        EXPECTED_DETAILS_ALL_JOBS,
        id="unfiltered_all_data",
    ),
    # 2. Filtered by date - last 24 hours
    pytest.param(
        build_recent_query(),
        EXPECTED_DETAILS_JOB_1_AND_2,
        id="filtered_by_date",
    ),
    # 3. Filtered by organization
    pytest.param(
        build_filtered_query(organization=[1]),
        EXPECTED_DETAILS_JOB_1_AND_2,
        id="filtered_by_organization",
    ),
    # 4. Filtered by template_id
    pytest.param(
        build_filtered_query(template=[1]),
        EXPECTED_DETAILS_JOB_1_AND_2,
        id="filtered_by_template",
    ),
    # 5. Filtered by project
    pytest.param(
        build_filtered_query(project=[1]),
        EXPECTED_DETAILS_JOB_1_AND_2,
        id="filtered_by_project",
    ),
    # 6. Filtered by labels
    pytest.param(
        build_filtered_query(label=[1]),
        EXPECTED_DETAILS_JOB_1_AND_2,
        id="filtered_by_labels",
    ),
]


# =============================================================================
# Helper functions for test assertions
# =============================================================================


def assert_numeric_equal(actual, expected, key: str, tolerance: float = 0.01):
    """Assert that two numeric values are equal within tolerance."""
    if isinstance(actual, int | float) or hasattr(actual, "__float__"):
        actual = float(actual)
    if isinstance(expected, int | float):
        expected = float(expected)

    if isinstance(actual, float) and isinstance(expected, float):
        assert abs(actual - expected) < tolerance, f"Expected {key}='{expected}' in response, but got '{actual}'"
    else:
        assert actual == expected, f"Expected {key}='{expected}' in response, but got '{actual}'"


def assert_valid_iso_datetime(label: str):
    """Assert that label is a valid ISO datetime string."""
    assert isinstance(label, str), f"Expected label to be str, got {type(label)}"
    try:
        datetime.datetime.fromisoformat(label.replace("Z", "+00:00"))
    except ValueError:
        pytest.fail(f"Invalid ISO datetime format in label: {label}")


def assert_chart_item_valid(item: dict, chart_name: str):
    """Assert that a chart item has valid structure and values."""
    assert "label" in item, f"Missing 'label' in {chart_name} item"
    assert "value" in item, f"Missing 'value' in {chart_name} item"
    assert_valid_iso_datetime(item["label"])
    assert isinstance(item["value"], int), f"Expected value to be int, got {type(item['value'])}"


def assert_chart_structure(data: dict):
    """Assert that job_chart and host_chart have correct structure."""
    for chart_name in ["job_chart", "host_chart"]:
        assert chart_name in data, f"Missing {chart_name} in response"
        chart = data[chart_name]
        assert "kind" in chart, f"Missing 'kind' in {chart_name}"
        assert "items" in chart, f"Missing 'items' in {chart_name}"
        assert isinstance(chart["items"], list), f"{chart_name} items should be a list"

        if chart["items"]:
            assert_chart_item_valid(chart["items"][0], chart_name)


def assert_chart_data(
    chart: dict,
    chart_name: str,
    expected_kind: str,
    expected_total: int,
    expected_non_zero_count: int | None = None,
    expected_values: list[int] | None = None,
):
    """
    Assert chart data is correct.

    Args:
        chart: The chart dict with 'kind' and 'items'
        chart_name: Name for error messages ('job_chart' or 'host_chart')
        expected_kind: Expected value for 'kind' field
        expected_total: Expected sum of all item values
        expected_non_zero_count: Expected number of items with value > 0
        expected_values: Expected sorted list of non-zero values
    """
    assert chart["kind"] == expected_kind, f"Expected {chart_name} kind='{expected_kind}', got '{chart['kind']}'"

    items = chart["items"]
    assert len(items) > 0, f"Expected {chart_name} to have items"

    non_zero_items = [item for item in items if item["value"] > 0]
    total = sum(item["value"] for item in items)

    assert total == expected_total, f"Expected {chart_name} total={expected_total}, got {total}"

    if expected_non_zero_count is not None:
        assert len(non_zero_items) == expected_non_zero_count, (
            f"Expected {expected_non_zero_count} {chart_name} items with value > 0, got {len(non_zero_items)}"
        )

    if expected_values is not None:
        actual_values = sorted([item["value"] for item in non_zero_items])
        assert actual_values == expected_values, f"Expected {chart_name} values {expected_values}, got {actual_values}"

    # Validate each non-zero item
    for item in non_zero_items:
        assert_chart_item_valid(item, chart_name)
        assert item["value"] > 0, f"Expected positive value in non-zero {chart_name} items"

    return non_zero_items


# =============================================================================
# Test class for report view data (default settings)
# =============================================================================


@pytest.mark.unit
@pytest.mark.django_db(transaction=True, reset_sequences=True)
class TestReportViewData:
    """Tests for report view with default SubscriptionCost settings."""

    @pytest.mark.parametrize("query, expected_count, expected_data", TEST_REPORT_VIEW_CASES)
    def test_report_view(self, job_data, query, expected_count, expected_data):
        """Test report list endpoint with various filters."""
        url = reverse("dashboard_reports:report-list")
        response = APIClient().get(url, data=query)

        assert response.status_code == 200
        data = response.data
        assert data["count"] == expected_count
        assert len(data["results"]) == expected_count

        for i, expected_item in enumerate(expected_data):
            for key, value in expected_item.items():
                assert key in data["results"][i], f"Missing key '{key}' in result {i}"
                assert data["results"][i][key] == value, (
                    f"Expected {key}='{value}' in result {i}, got '{data['results'][i][key]}'"
                )

    @pytest.mark.parametrize("query, expected_data", TEST_REPORT_VIEW_DETAIL_CASES)
    def test_report_view_details(self, job_data, query, expected_data):
        """Test report details endpoint with various filters."""
        url = reverse("dashboard_reports:report-details")
        response = APIClient().get(url, data=query)

        assert response.status_code == 200
        data = response.data

        # Verify expected values
        for key, value in expected_data.items():
            assert key in data, f"Missing key '{key}' in response"
            assert_numeric_equal(data[key], value, key)

        # Verify chart structure
        assert_chart_structure(data)

    def test_report_view_details_charts_data(self, job_data):
        """Test that job_chart and host_chart contain correct data values for recent jobs."""
        url = reverse("dashboard_reports:report-details")
        response = APIClient().get(url, data=build_recent_query())

        assert response.status_code == 200
        data = response.data

        # Verify job_chart: kind='hour', total=2 (job_id 1 and 2)
        job_non_zero = assert_chart_data(
            data["job_chart"],
            "job_chart",
            expected_kind="hour",
            expected_total=2,
        )

        # Verify host_chart: kind='hour', total=20 (num_hosts for job 1 and 2)
        host_non_zero = assert_chart_data(
            data["host_chart"],
            "host_chart",
            expected_kind="hour",
            expected_total=20,
        )

        # Verify that job and host charts have same labels (same time buckets)
        job_labels = {item["label"] for item in job_non_zero}
        host_labels = {item["label"] for item in host_non_zero}
        assert job_labels == host_labels, f"Job and host chart labels should match: {job_labels} vs {host_labels}"

    def test_report_view_details_charts_unfiltered(self, job_data):
        """Test job_chart and host_chart data for unfiltered (all jobs) query."""
        url = reverse("dashboard_reports:report-details")
        response = APIClient().get(url, data=build_filtered_query())

        assert response.status_code == 200
        data = response.data

        # Verify job_chart: kind='day', total=4, 2 days with 2 jobs each
        job_non_zero = assert_chart_data(
            data["job_chart"],
            "job_chart",
            expected_kind="day",
            expected_total=4,
            expected_non_zero_count=2,
            expected_values=[2, 2],
        )

        # Verify host_chart: kind='day', total=22, today=20 hosts, 5 days ago=2 hosts
        host_non_zero = assert_chart_data(
            data["host_chart"],
            "host_chart",
            expected_kind="day",
            expected_total=22,
            expected_non_zero_count=2,
            expected_values=[2, 20],
        )

        # Verify that job and host charts have same labels (same time buckets)
        job_labels = {item["label"] for item in job_non_zero}
        host_labels = {item["label"] for item in host_non_zero}
        assert job_labels == host_labels, f"Job and host chart labels should match: {job_labels} vs {host_labels}"


# =============================================================================
# Expected data when include_template_creation_time_in_costs=False
# =============================================================================
# When this setting is False:
# - automated_costs does NOT include template creation time cost
# - time_savings does NOT subtract template creation time

EXPECTED_TEMPLATE_A_NO_CREATION_TIME = {
    "template_name": "Template A",
    "template_metadata_id": 1,
    "time_taken_manually_execute_minutes": 240,
    "time_taken_create_automation_minutes": 40,
    "runs": 2,
    "successful_runs": 1,
    "failed_runs": 1,
    "elapsed": "65.00",
    "elapsed_str": "1min 5sec",
    "automated_costs": "0.12",
    "manual_costs": "4800.00",
    "time_savings": "287935.00",
    "time_savings_str": "79h 58min 55sec",
    "savings": "4799.88",
}

EXPECTED_DETAILS_NO_CREATION_TIME = {
    "total_number_of_job_runs": 2,
    "total_number_of_successful_jobs": 1,
    "total_number_of_failed_jobs": 1,
    "total_number_of_host_job_runs": 20,
    "total_number_of_unique_hosts": 3,
    "total_hours_of_automation": 0.02,
    "cost_of_automated_execution": 0.12,
    "cost_of_manual_automation": 4800.0,
    "total_saving": 4799.88,
    "total_time_saving": 79.98,
    "top_users": [
        {"id": 1, "user_name": "test_user", "execution_count": 2},
    ],
    "top_projects": [
        {"id": 1, "project_name": "Project A", "execution_count": 2},
    ],
}


# =============================================================================
# Test class for report view with include_template_creation_time_in_costs=False
# =============================================================================


@pytest.mark.unit
@pytest.mark.django_db(transaction=True, reset_sequences=True)
class TestReportViewDataNoCreationTime:
    """
    Tests for report view when SubscriptionCost.include_template_creation_time_in_costs=False.

    When this setting is False:
    - automated_costs does NOT include template creation time cost
    - time_savings does NOT subtract template creation time
    """

    @pytest.fixture(autouse=True)
    def setup_subscription_cost(self):
        """Set include_template_creation_time_in_costs=False for all tests in this class."""
        subscription_cost = SubscriptionCost.get()
        original_value = subscription_cost.include_template_creation_time_in_costs
        subscription_cost.include_template_creation_time_in_costs = False
        subscription_cost.save()
        yield
        # Reset to original value after test
        subscription_cost.include_template_creation_time_in_costs = original_value
        subscription_cost.save()

    def test_report_view_no_creation_time(self, job_data):
        """Test report view calculations when include_template_creation_time_in_costs=False."""
        url = reverse("dashboard_reports:report-list")
        response = APIClient().get(url, data=build_recent_query())

        assert response.status_code == 200
        data = response.data
        assert data["count"] == 1

        # Verify calculations without template creation time
        result = data["results"][0]
        for key, value in EXPECTED_TEMPLATE_A_NO_CREATION_TIME.items():
            assert key in result, f"Missing key '{key}' in result"
            assert result[key] == value, f"Expected {key}='{value}', got '{result[key]}'"

    def test_report_view_details_no_creation_time(self, job_data):
        """Test report details calculations when include_template_creation_time_in_costs=False."""
        url = reverse("dashboard_reports:report-details")
        response = APIClient().get(url, data=build_recent_query())

        assert response.status_code == 200
        data = response.data

        # Verify calculations without template creation time
        for key, value in EXPECTED_DETAILS_NO_CREATION_TIME.items():
            assert key in data, f"Missing key '{key}' in response"
            assert_numeric_equal(data[key], value, key)

        # Verify chart structure
        assert_chart_structure(data)
