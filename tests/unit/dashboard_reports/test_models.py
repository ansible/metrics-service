"""Unit tests for Dashboard Reports model."""

import datetime
import decimal

import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError

from apps.dashboard_reports.models import (
    FilterSet,
    JobData,
    JobHostSummary,
    JobLabel,
    JobStatusChoices,
    SubscriptionCost,
    TemplateMetadata,
)

User = get_user_model()


@pytest.fixture
def user():
    """Fixture to create a test user."""
    return User.objects.create_user(username="testuser", email="test@example.com", password="testpassword123")  # noqa: S105


@pytest.fixture
def template_metadata():
    """Fixture to create a TemplateMetadata instance."""
    return TemplateMetadata.objects.create(
        template_id=1,
        template_name="Template 1",
        time_taken_manually_execute_minutes=60,
        time_taken_create_automation_minutes=20,
    )


@pytest.fixture
def job_data(template_metadata):
    """Fixture to create a JobData instance."""
    return JobData.objects.create(
        job_id=1,
        template_name="Template 1",
        template_id=1,
        project_id=1,
        project_name="Project 1",
        organization_id=1,
        status="successful",
        started=datetime.datetime.fromisoformat("2024-01-01T00:00:00Z"),
        finished=datetime.datetime.fromisoformat("2024-01-01T00:02:00Z"),
        elapsed=120.5,
        num_hosts=5,
        launched_by_id=1,
        launched_by_username="testuser",
        template_metadata=template_metadata,
    )


@pytest.mark.unit
@pytest.mark.django_db
class TestSubscriptionCost:
    """Test cases for SubscriptionCost model."""

    def test_subscription_cost_get_cost(self):
        """Test get_cost method of SubscriptionCost."""
        subscription_cost = SubscriptionCost.get()
        assert subscription_cost.monthly_subscription_cost == decimal.Decimal("5000.00")
        assert subscription_cost.engineer_avg_hourly_rate == decimal.Decimal("60.00")
        assert subscription_cost.include_template_creation_time_in_costs is True

    def test_subscription_cost_creation(self):
        """Test subscription cost can be created successfully."""
        subscription_cost = SubscriptionCost.objects.create(
            monthly_subscription_cost=100.00,
            engineer_avg_hourly_rate=15.00,
            include_template_creation_time_in_costs=False,
        )
        assert subscription_cost.monthly_subscription_cost == decimal.Decimal("100.00")
        assert subscription_cost.engineer_avg_hourly_rate == decimal.Decimal("15.00")
        assert subscription_cost.include_template_creation_time_in_costs is False

    def test_subscription_cost_string_representation(self):
        """Test subscription cost string representation."""
        subscription_cost = SubscriptionCost.objects.create(
            monthly_subscription_cost=100.00,
            engineer_avg_hourly_rate=15.00,
            include_template_creation_time_in_costs=False,
        )
        expected_str = f"SubscriptionCost: Monthly={subscription_cost.monthly_subscription_cost}, Engineer Hourly Rate={subscription_cost.engineer_avg_hourly_rate}"
        assert str(subscription_cost) == expected_str

    def test_subscription_cost_singleton_behavior(self):
        """Test that SubscriptionCost behaves like a singleton."""
        subscription_cost1 = SubscriptionCost.get()
        subscription_cost2 = SubscriptionCost.get()
        assert subscription_cost1 == subscription_cost2
        assert SubscriptionCost.objects.count() == 1
        SubscriptionCost.objects.create(
            monthly_subscription_cost=100.00,
            engineer_avg_hourly_rate=15.00,
            include_template_creation_time_in_costs=False,
        )
        assert SubscriptionCost.objects.count() == 1
        subscription_cost3 = SubscriptionCost.get()
        assert subscription_cost3.monthly_subscription_cost == decimal.Decimal("100.00")
        assert subscription_cost3.engineer_avg_hourly_rate == decimal.Decimal("15.00")
        assert subscription_cost3.include_template_creation_time_in_costs is False


@pytest.mark.unit
@pytest.mark.django_db
class TestFilterSet:
    """Test cases for FilterSet model."""

    def test_filter_set_creation(self, user):
        """Test filter set can be created successfully."""
        filter_set = FilterSet.objects.create(
            name="Test Filter Set", filters={"key": "value"}, user=user, is_default=True
        )
        assert filter_set.name == "Test Filter Set"
        assert filter_set.filters == {"key": "value"}
        assert filter_set.user == user
        assert filter_set.is_default is True

    def test_filter_set_string_representation(self, user):
        """Test filter set string representation."""
        filter_set = FilterSet.objects.create(
            name="Test Filter Set", filters={"key": "value"}, user=user, is_default=True
        )
        assert str(filter_set) == "Test Filter Set"

    def test_filter_set_default_behavior(self, user):
        """Test that only one default FilterSet exists per user."""
        FilterSet.objects.create(name="Default Filter Set", filters={"key": "value"}, user=user, is_default=True)
        with pytest.raises(IntegrityError):
            FilterSet.objects.create(
                name="Another Default Filter Set", filters={"key": "value"}, user=user, is_default=True
            )


@pytest.mark.unit
@pytest.mark.django_db
class TestTemplateMetadata:
    """Test cases for TemplateMetadata model."""

    def test_template_metadata_creation(self, template_metadata):
        """Test template metadata can be created successfully."""
        assert template_metadata.template_id == 1
        assert template_metadata.template_name == "Template 1"
        assert template_metadata.time_taken_manually_execute_minutes == 60
        assert template_metadata.time_taken_create_automation_minutes == 20

    def test_template_metadata_string_representation(self, template_metadata):
        """Test template metadata string representation."""
        expected_str = f"Metadata for {template_metadata.template_name} (ID: {template_metadata.template_id})"
        assert str(template_metadata) == expected_str

    def test_template_metadata_unique_template_id(self, template_metadata):
        """Test that template_id is unique."""
        with pytest.raises(IntegrityError):
            TemplateMetadata.objects.create(
                template_id=1,
                template_name="Duplicate Template",
                time_taken_manually_execute_minutes=30,
                time_taken_create_automation_minutes=10,
            )

    def test_template_metadata_update_time_fields(self, template_metadata):
        """Test updating time fields of TemplateMetadata."""
        template_metadata.time_taken_manually_execute_minutes = 45
        template_metadata.time_taken_create_automation_minutes = 15
        template_metadata.save()
        template_metadata.refresh_from_db()
        assert template_metadata.time_taken_manually_execute_minutes == 45
        assert template_metadata.time_taken_create_automation_minutes == 15


@pytest.mark.unit
@pytest.mark.django_db
class TestJobData:
    """Test cases for JobData model."""

    def test_job_data_creation(self, job_data, template_metadata):
        """Test job data can be created successfully."""
        job_data.refresh_from_db()
        assert job_data.job_id == 1
        assert job_data.template_name == "Template 1"
        assert job_data.template_id == 1
        assert job_data.project_id == 1
        assert job_data.project_name == "Project 1"
        assert job_data.organization_id == 1
        assert job_data.status == JobStatusChoices.SUCCESSFUL
        assert job_data.started == datetime.datetime.fromisoformat("2024-01-01T00:00:00Z")
        assert job_data.finished == datetime.datetime.fromisoformat("2024-01-01T00:02:00Z")
        assert job_data.elapsed == decimal.Decimal("120.5")
        assert job_data.num_hosts == 5
        assert job_data.launched_by_id == 1
        assert job_data.launched_by_username == "testuser"
        assert job_data.template_metadata == template_metadata

    def test_job_data_string_representation(self, job_data):
        """Test job data string representation."""
        expected_str = f"Job {job_data.job_id} - Template: {job_data.template_name} - Status: {job_data.status}"
        assert str(job_data) == expected_str

    def test_job_data_update_status(self, job_data):
        """Test updating the status of JobData."""
        job_data.status = JobStatusChoices.FAILED
        job_data.save()
        job_data.refresh_from_db()
        assert job_data.status == JobStatusChoices.FAILED

    def test_job_data_unique_job_id(self, job_data):
        """Test that job_id is unique."""
        with pytest.raises(IntegrityError):
            JobData.objects.create(
                job_id=1,
                template_name="Another Template",
                template_id=2,
                project_id=2,
                project_name="Project 2",
                organization_id=2,
                status="failed",
                started=datetime.datetime.fromisoformat("2024-01-02T00:00:00Z"),
                finished=datetime.datetime.fromisoformat("2024-01-02T00:05:00Z"),
                elapsed=300.0,
                num_hosts=10,
                launched_by_id=1,
                launched_by_username="testuser",
                template_metadata=None,
            )


@pytest.mark.unit
@pytest.mark.django_db
class TestJobStatusChoices:
    """Test cases for JobStatusChoices."""

    def test_job_status_choices(self):
        """Test that JobStatusChoices contains expected values."""
        assert JobStatusChoices.NEW == "new"
        assert JobStatusChoices.PENDING == "pending"
        assert JobStatusChoices.WAITING == "waiting"
        assert JobStatusChoices.RUNNING == "running"
        assert JobStatusChoices.SUCCESSFUL == "successful"
        assert JobStatusChoices.FAILED == "failed"
        assert JobStatusChoices.ERROR == "error"
        assert JobStatusChoices.CANCELED == "canceled"


@pytest.mark.unit
@pytest.mark.django_db
class TestJobLabel:
    def test_job_label_creation(self, job_data):
        """Test JobLabel can be created successfully."""
        label = JobLabel.objects.create(
            job_data=job_data,
            label_id=1,
        )
        label.refresh_from_db()
        assert label.job_data == job_data
        assert label.label_id == 1

    def test_job_label_string_representation(self, job_data):
        """Test JobLabel string representation."""
        label = JobLabel.objects.create(
            job_data=job_data,
            label_id=1,
        )
        label.refresh_from_db()
        expected_str = f"{label.job_data.template_name}: {label.label_id}"
        assert str(label) == expected_str


@pytest.mark.unit
@pytest.mark.django_db
class TestJobHostSummary:
    def test_job_host_summary_creation(self, job_data):
        """Test JobHostSummary can be created successfully."""
        host_summary = JobHostSummary.objects.create(
            job_data=job_data,
            host_summary_id=1,
            host_id=2,
            host_name="host2",
        )
        host_summary.refresh_from_db()
        assert host_summary.job_data == job_data
        assert host_summary.host_summary_id == 1
        assert host_summary.host_id == 2
        assert host_summary.host_name == "host2"

    def test_job_host_summary_string_representation(self, job_data):
        """Test JobHostSummary string representation."""
        host_summary = JobHostSummary.objects.create(
            job_data=job_data,
            host_summary_id=1,
            host_id=2,
            host_name="host2",
        )
        host_summary.refresh_from_db()
        expected_str = f"{host_summary.host_name}: {host_summary.job_data.template_name}"
        assert str(host_summary) == expected_str

    def test_job_host_summary_unique_host_summary_id(self, job_data):
        """Test that host_summary_id is unique."""
        JobHostSummary.objects.create(
            job_data=job_data,
            host_summary_id=1,
            host_id=2,
            host_name="host2",
        )
        with pytest.raises(IntegrityError):
            JobHostSummary.objects.create(
                job_data=job_data,
                host_summary_id=1,
                host_id=3,
                host_name="host3",
            )
