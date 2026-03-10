"""Unit tests for Dashboard Reports model."""

import datetime
import decimal

import pytest
import pytz
from django.contrib.auth import get_user_model
from django.db import IntegrityError

from apps.dashboard_reports.models import (
    DEFAULT_TIME_TAKEN_TO_CREATE_AUTOMATION_MINUTES,
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

    def test_min_awx_id_minus_one(self):
        """Test TemplateMetadata.get_min_awx_id returns -1 when no records exist."""
        assert TemplateMetadata.get_min_awx_id() == -1

    def test_min_awx_id_positive_ids(self, template_metadata):
        """Test TemplateMetadata.get_min_awx_id returns -1 when only positive template_ids exist."""
        TemplateMetadata.objects.create(
            template_id=10,
            template_name="Test Positive",
            time_taken_manually_execute_minutes=30,
            time_taken_create_automation_minutes=10,
        )
        TemplateMetadata.objects.create(
            template_id=20,
            template_name="Test Positive 2",
            time_taken_manually_execute_minutes=30,
            time_taken_create_automation_minutes=10,
        )
        assert TemplateMetadata.get_min_awx_id() == -1

    def test_min_awx_id_negative_ids(self, template_metadata):
        """Test TemplateMetadata.get_min_awx_id returns min template_id minus one when negative template_ids exist."""
        TemplateMetadata.objects.create(
            template_id=-5,
            template_name="Test Negative",
            time_taken_manually_execute_minutes=30,
            time_taken_create_automation_minutes=10,
        )
        TemplateMetadata.objects.create(
            template_id=-10,
            template_name="Test Negative 2",
            time_taken_manually_execute_minutes=30,
            time_taken_create_automation_minutes=10,
        )
        assert TemplateMetadata.get_min_awx_id() == -11

    def test_min_awx_id_mixed_ids(self, template_metadata):
        """Test TemplateMetadata.get_min_awx_id returns min template_id minus one if negative template_ids exist, even if positive template_ids also exist."""
        TemplateMetadata.objects.create(
            template_id=10,
            template_name="Test Positive",
            time_taken_manually_execute_minutes=30,
            time_taken_create_automation_minutes=10,
        )
        TemplateMetadata.objects.create(
            template_id=-3,
            template_name="Test Negative",
            time_taken_manually_execute_minutes=30,
            time_taken_create_automation_minutes=10,
        )
        assert TemplateMetadata.get_min_awx_id() == -4

    def test_retrieve_by_awx_id(self):
        obj = TemplateMetadata.objects.create(template_id=42, template_name="Test")
        result = TemplateMetadata.get_by_awx_id_or_name(name="Other", awx_id=42)
        assert result.pk == obj.pk

    def test_retrieve_by_name(self):
        obj = TemplateMetadata.objects.create(template_id=99, template_name="TestName")
        result = TemplateMetadata.get_by_awx_id_or_name(name="TestName")
        assert result.pk == obj.pk

    def test_create_new_when_none_exist(self):
        result = TemplateMetadata.get_by_awx_id_or_name(name="NewTemplate", awx_id=123)
        assert result.template_name == "NewTemplate"
        assert result.template_id == 123

    def test_awx_id_and_name_both_provided_awx_id_exists(self):
        obj = TemplateMetadata.objects.create(template_id=7, template_name="AWXTemplate")
        result = TemplateMetadata.get_by_awx_id_or_name(name="AWXTemplate", awx_id=7)
        assert result.pk == obj.pk

    def test_awx_id_and_name_both_provided_name_exists(self):
        obj = TemplateMetadata.objects.create(template_id=8, template_name="NameTemplate")
        result = TemplateMetadata.get_by_awx_id_or_name(name="NameTemplate", awx_id=999)
        assert result.pk == obj.pk
        assert result.template_id == 8

    def test_elapsed_sets_manual_time_estimate(self):
        result = TemplateMetadata.get_by_awx_id_or_name(
            name="ElapsedTemplate", awx_id=55, elapsed=decimal.Decimal(3600)
        )
        # 2x elapsed (3600s = 60min), so 2x60 = 120min, min 30
        assert result.time_taken_manually_execute_minutes == 120

    def test_automation_time_estimate_default(self):
        result = TemplateMetadata.get_by_awx_id_or_name(name="AutoTemplate", awx_id=66)
        assert result.time_taken_create_automation_minutes == DEFAULT_TIME_TAKEN_TO_CREATE_AUTOMATION_MINUTES


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

    def test_latest_timestamp_returns_none(self):
        assert JobData.last_timestamp() is None

    def test_all_records_null_awx_modified_returns_none(self):
        JobData.objects.create(job_id=1, template_name="T1", elapsed=1)
        JobData.objects.create(job_id=2, template_name="T2", elapsed=2)
        assert JobData.last_timestamp() is None

    def test_returns_latest_awx_modified(self):
        now = datetime.datetime.now().astimezone(pytz.utc)
        earlier = (now - datetime.timedelta(days=1)).astimezone(pytz.utc)
        later = (now + datetime.timedelta(days=1)).astimezone(pytz.utc)
        JobData.objects.create(job_id=3, template_name="T3", elapsed=3, awx_modified=earlier)
        JobData.objects.create(job_id=4, template_name="T4", elapsed=4, awx_modified=now)
        JobData.objects.create(job_id=5, template_name="T5", elapsed=5, awx_modified=later)
        assert JobData.last_timestamp() == later

    def test_mixed_null_and_valid_awx_modified(self):
        now = datetime.datetime.now().astimezone(pytz.utc)
        JobData.objects.create(job_id=6, template_name="T6", elapsed=6, awx_modified=None)
        JobData.objects.create(job_id=7, template_name="T7", elapsed=7, awx_modified=now)
        assert JobData.last_timestamp() == now


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


@pytest.mark.unit
@pytest.mark.django_db
class TestJobDataCreateOrUpdateFromAWX:
    def setup_method(self):
        self.awx_job_base = {
            "id": 100,
            "name": "Test Template",
            "unified_job_template_id": 200,
            "project_id": 300,
            "project_name": "Test Project",
            "organization_id": 400,
            "status": "successful",
            "started": datetime.datetime(2024, 1, 1, 10, 0, 0).astimezone(pytz.utc),
            "finished": datetime.datetime(2024, 1, 1, 11, 0, 0).astimezone(pytz.utc),
            "elapsed": decimal.Decimal("3600.0"),
            "launched_by_id": 500,
            "launched_by_username": "testuser",
            "created": datetime.datetime(2024, 1, 1, 9, 59, 0).astimezone(pytz.utc),
            "modified": datetime.datetime(2024, 1, 1, 11, 1, 0).astimezone(pytz.utc),
            "num_hosts": 2,
            "labels": [1, 2],
            "host_summaries": [
                {"id": 10, "host_id": 1000, "host_name": "host1"},
                {"id": 11, "host_id": 1001, "host_name": "host2"},
            ],
        }

    def test_create_new_job_data_and_related(self):
        JobData.create_or_update_from_awx(self.awx_job_base)
        job = JobData.objects.get(job_id=100)
        assert job.template_name == "Test Template"
        assert job.status == "successful"
        assert job.num_hosts == 2
        assert job.elapsed == decimal.Decimal("3600.0")
        assert job.finished == datetime.datetime(2024, 1, 1, 11, 0, 0).astimezone(pytz.utc)
        # TemplateMetadata created
        assert TemplateMetadata.objects.filter(template_id=200).exists()
        # JobLabels created
        labels = list(JobLabel.objects.filter(job_data=job).values_list("label_id", flat=True))
        assert set(labels) == {1, 2}
        # HostSummaries created
        hosts = list(JobHostSummary.objects.filter(job_data=job).values_list("host_summary_id", flat=True))
        assert set(hosts) == {10, 11}

    def test_update_existing_job_data_and_labels_hosts(self):
        # First create
        JobData.create_or_update_from_awx(self.awx_job_base)
        # Now update: remove label 2, add label 3, update host 10, remove host 11, add host 12
        awx_job_update = self.awx_job_base.copy()
        awx_job_update["labels"] = [1, 3]
        awx_job_update["host_summaries"] = [
            {"id": 10, "host_id": 1000, "host_name": "host1-updated"},
            {"id": 12, "host_id": 1002, "host_name": "host3"},
        ]
        JobData.create_or_update_from_awx(awx_job_update)
        job = JobData.objects.get(job_id=100)
        # Labels: 1 and 3 should exist
        labels = list(JobLabel.objects.filter(job_data=job).values_list("label_id", flat=True))
        assert set(labels) == {1, 3}
        # HostSummaries: 10 and 12 should exist, 10 should be updated
        hosts = list(JobHostSummary.objects.filter(job_data=job).values_list("host_summary_id", flat=True))
        assert set(hosts) == {10, 12}
        host10 = JobHostSummary.objects.get(job_data=job, host_summary_id=10)
        assert host10.host_name == "host1-updated"

    def test_create_with_no_labels_or_hosts(self):
        awx_job = self.awx_job_base.copy()
        awx_job["labels"] = []
        awx_job["host_summaries"] = []
        JobData.create_or_update_from_awx(awx_job)
        job = JobData.objects.get(job_id=100)
        assert JobLabel.objects.filter(job_data=job).count() == 0
        assert JobHostSummary.objects.filter(job_data=job).count() == 0

    def test_template_metadata_created_if_missing(self):
        # Remove TemplateMetadata if exists
        TemplateMetadata.objects.filter(template_id=200).delete()
        JobData.create_or_update_from_awx(self.awx_job_base)
        assert TemplateMetadata.objects.filter(template_id=200).exists()
