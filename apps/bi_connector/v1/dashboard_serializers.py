"""
Serializers for BI connector dashboard endpoints.

Exposes JobData and TemplateMetadata in a flat columnar format for BI tool compatibility.
Template metadata time estimates are inlined into the JobData list serializer so BI tools
get a single joined row rather than a separate lookup.
"""

from rest_framework import serializers

from apps.dashboard_reports.models import JobData, TemplateMetadata


class TemplateMetadataSerializer(serializers.ModelSerializer):
    """Read-only serializer for TemplateMetadata billing data."""

    class Meta:
        """Serializer field configuration for TemplateMetadataSerializer."""

        model = TemplateMetadata
        fields = [
            "id",
            "template_id",
            "template_name",
            "time_taken_manually_execute_minutes",
            "time_taken_create_automation_minutes",
            "created",
            "modified",
        ]


class JobDataListSerializer(serializers.ModelSerializer):
    """
    Flat list serializer for BI tool consumption.

    Template metadata time estimates are inlined as top-level fields so BI tools
    receive a single joined row per job. The queryset must use select_related('template_metadata')
    to avoid N+1 queries.
    """

    template_time_manual_minutes = serializers.SerializerMethodField()
    template_time_automation_minutes = serializers.SerializerMethodField()

    class Meta:
        """Serializer field configuration for JobDataListSerializer."""

        model = JobData
        fields = [
            "id",
            "job_id",
            "template_name",
            "template_id",
            "project_id",
            "project_name",
            "organization_id",
            "organization_name",
            "status",
            "started",
            "finished",
            "elapsed",
            "num_hosts",
            "launched_by_id",
            "launched_by_username",
            "template_time_manual_minutes",
            "template_time_automation_minutes",
            "awx_created",
            "awx_modified",
            "created",
            "modified",
        ]

    def get_template_time_manual_minutes(self, obj: JobData):
        """Return manual execution time estimate from linked TemplateMetadata, or None."""
        return obj.template_metadata.time_taken_manually_execute_minutes if obj.template_metadata else None

    def get_template_time_automation_minutes(self, obj: JobData):
        """Return automation creation time estimate from linked TemplateMetadata, or None."""
        return obj.template_metadata.time_taken_create_automation_minutes if obj.template_metadata else None


class JobDataDetailSerializer(JobDataListSerializer):
    """
    Detail serializer — adds label IDs and host summaries for the individual job view.
    """

    label_ids = serializers.SerializerMethodField()
    host_summaries = serializers.SerializerMethodField()

    class Meta(JobDataListSerializer.Meta):
        """Extends list serializer fields with label IDs and host summaries."""

        fields = JobDataListSerializer.Meta.fields + ["label_ids", "host_summaries"]

    def get_label_ids(self, obj: JobData) -> list:
        """Return list of label IDs associated with this job."""
        return list(obj.labels.values_list("label_id", flat=True))

    def get_host_summaries(self, obj: JobData) -> list:
        """Return list of host summary dicts for this job."""
        return list(obj.host_summaries.values("host_summary_id", "host_id", "host_name"))
