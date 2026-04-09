from typing import Any

from dateutil.relativedelta import relativedelta
from rest_framework import serializers

from apps.dashboard_reports.models import JobData, TemplateMetadata


def sec2time(sec: int) -> str:
    """
    This function converts a number of seconds into a human-readable string format,
    displaying hours, minutes, and seconds.
    It uses `relativedelta` to break down the total seconds and combines days into hours for the output.
    If the total time is less than one hour, it omits the hours part for brevity.
    """
    rd = relativedelta(seconds=sec)
    hours = rd.hours + (24 * rd.days)
    secs = round(rd.seconds)
    return f"{hours}h {rd.minutes}min {secs}sec" if hours > 0 else f"{rd.minutes}min {secs}sec"


class FilterOptionWithIdSerializer(serializers.Serializer):
    id = serializers.IntegerField(help_text="Option ID")
    name = serializers.CharField(help_text="Option display name")


class PaginatedFilterOptionsSerializer(serializers.Serializer):
    """
    Paginated response serializer for filter options.

    Matches the OptionsResponse TypeScript interface from automation-reports:
        interface OptionsResponse {
            count: number;
            next: string | null;
            previous: string | null;
            results: FilterOptionWithId[];
        }
    """

    count = serializers.IntegerField(help_text="Total number of options available")
    next = serializers.CharField(allow_null=True, help_text="URL to next page (null if last page)")
    previous = serializers.CharField(allow_null=True, help_text="URL to previous page (null if first page)")
    results = FilterOptionWithIdSerializer(many=True, help_text="Array of filter options in {id, name} format")


class ReportSerializer(serializers.ModelSerializer[JobData]):
    id = serializers.IntegerField(source="template_id", read_only=True)
    time_taken_manually_execute_minutes = serializers.IntegerField(
        read_only=True, help_text="Estimated time to perform this task manually (minutes)"
    )
    time_taken_create_automation_minutes = serializers.IntegerField(
        read_only=True, help_text="Estimated time spent creating this automation (minutes)"
    )
    runs = serializers.IntegerField(read_only=True, help_text="Total number of times this job template was executed")
    successful_runs = serializers.IntegerField(read_only=True, help_text="Number of successful runs")
    failed_runs = serializers.IntegerField(read_only=True, help_text="Number of failed runs")
    elapsed = serializers.DecimalField(
        max_digits=10, decimal_places=2, help_text="Total elapsed time for all runs (seconds)"
    )
    elapsed_str = serializers.SerializerMethodField(help_text="Total elapsed time for all runs (human-readable string)")
    automated_costs = serializers.DecimalField(
        max_digits=20, decimal_places=2, read_only=True, help_text="Estimated costs of running this job template on AAP"
    )
    manual_costs = serializers.DecimalField(
        max_digits=20, decimal_places=2, read_only=True, help_text="Estimated costs if all jobs were run manually"
    )
    time_savings = serializers.DecimalField(
        max_digits=20,
        decimal_places=2,
        read_only=True,
        help_text="Estimated time savings in seconds by automating this job template",
    )
    time_savings_str = serializers.SerializerMethodField(
        help_text="Estimated time savings by automating this job template (human-readable string)"
    )
    savings = serializers.DecimalField(
        max_digits=20,
        decimal_places=2,
        read_only=True,
        help_text="Estimated cost savings by automating this job template",
    )

    class Meta:
        model = JobData
        fields = (
            "template_name",
            "id",
            "time_taken_manually_execute_minutes",
            "time_taken_create_automation_minutes",
            "runs",
            "successful_runs",
            "failed_runs",
            "elapsed",
            "elapsed_str",
            "automated_costs",
            "manual_costs",
            "time_savings",
            "time_savings_str",
            "savings",
        )

    def _get_time_str(self, obj: dict[str, Any], key: str) -> str:
        """Helper to convert a time field to human-readable string."""
        value = obj.get(key)
        if value is None:
            return ""
        if value < 0:
            return f"-{sec2time(-value)}"
        return sec2time(value)

    def get_elapsed_str(self, obj: dict[str, Any]) -> str:
        return self._get_time_str(obj, "elapsed")

    def get_time_savings_str(self, obj: dict[str, Any]) -> str:
        return self._get_time_str(obj, "time_savings")


class TopUserSerializer(serializers.Serializer):
    id = serializers.IntegerField(
        read_only=True, source="launched_by_id", help_text="ID of the user who executed the job"
    )

    name = serializers.CharField(
        read_only=True, source="launched_by_username", help_text="Username of the user who executed the job"
    )

    execution_count = serializers.IntegerField(
        read_only=True, source="count", help_text="Number of times this user executed a job"
    )


class TopProjectSerializer(serializers.Serializer):
    id = serializers.IntegerField(
        read_only=True, source="project_id", help_text="ID of the project associated with the job"
    )

    name = serializers.CharField(
        read_only=True, source="project_name", help_text="Name of the project associated with the job"
    )

    execution_count = serializers.IntegerField(
        read_only=True, source="count", help_text="Number of times jobs associated with this project were executed"
    )


class ChartDataItemSerializer(serializers.Serializer):
    label = serializers.DateTimeField(read_only=True, help_text="Label for the data point (e.g. timestamp)")
    value = serializers.IntegerField(read_only=True, help_text="Value for the data point (e.g. number of job runs)")


class ReportChartSerializer(serializers.Serializer):
    kind = serializers.CharField(
        read_only=True, help_text="Type of date range for the series (e.g. hour, day, month, year)"
    )
    items = ChartDataItemSerializer(many=True, read_only=True, help_text="Data points for the chart series")


class ReportDetailSerializer(serializers.Serializer):
    total_number_of_job_runs = serializers.IntegerField(
        read_only=True, source="total_runs", help_text="Total number of job runs"
    )
    total_number_of_successful_jobs = serializers.IntegerField(
        read_only=True, source="total_successful_runs", help_text="Total number of successful job runs"
    )
    total_number_of_failed_jobs = serializers.IntegerField(
        read_only=True, source="total_failed_runs", help_text="Total number of failed job runs"
    )
    total_number_of_host_job_runs = serializers.IntegerField(
        read_only=True,
        source="total_num_hosts",
        help_text="Total number of host job runs (sum of all hosts across all jobs)",
    )
    total_hours_of_automation = serializers.SerializerMethodField(help_text="Total hours of automation")
    cost_of_automated_execution = serializers.SerializerMethodField(help_text="Total cost of automated execution")
    cost_of_manual_automation = serializers.SerializerMethodField(help_text="Total cost of manual execution")
    total_saving = serializers.SerializerMethodField(
        help_text="Total savings from automation (manual costs - automated costs)"
    )
    total_time_saving = serializers.SerializerMethodField(help_text="Total time savings from automation (in hours)")
    total_number_of_unique_hosts = serializers.IntegerField(
        read_only=True, help_text="Total number of unique hosts across all job runs"
    )

    top_users = TopUserSerializer(many=True, read_only=True, help_text="List of top users who executed the most jobs")

    top_projects = TopProjectSerializer(
        many=True, read_only=True, help_text="List of top projects associated with the most job executions"
    )

    job_chart = ReportChartSerializer(read_only=True, help_text="Chart data showing job executions over time")

    host_chart = ReportChartSerializer(read_only=True, help_text="Chart data showing host job runs over time")

    def _get_rounded_value(self, obj: dict[str, Any], key: str, divisor: float = 1) -> float:
        """Helper to get a rounded value from obj, optionally dividing by a divisor."""
        value = obj.get(key)
        return round(value / divisor, 2) if value is not None else 0

    def get_total_hours_of_automation(self, obj: dict[str, Any]) -> float:
        return self._get_rounded_value(obj, "total_elapsed", divisor=3600)

    def get_cost_of_automated_execution(self, obj: dict[str, Any]) -> float:
        return self._get_rounded_value(obj, "total_automated_costs")

    def get_cost_of_manual_automation(self, obj: dict[str, Any]) -> float:
        return self._get_rounded_value(obj, "total_manual_costs")

    def get_total_saving(self, obj: dict[str, Any]) -> float:
        return self._get_rounded_value(obj, "total_savings")

    def get_total_time_saving(self, obj: dict[str, Any]) -> float:
        return self._get_rounded_value(obj, "total_time_savings", divisor=3600)


class TemplateMetadataSerializer(serializers.ModelSerializer):
    template_id = serializers.IntegerField(read_only=True, help_text="ID of the associated job template")
    time_taken_manually_execute_minutes = serializers.IntegerField(
        allow_null=True, min_value=0, help_text="User override: Estimated time to perform this task manually (minutes)"
    )
    time_taken_create_automation_minutes = serializers.IntegerField(
        allow_null=True, min_value=0, help_text="User override: Estimated time spent creating this automation (minutes)"
    )

    class Meta:
        model = TemplateMetadata
        fields = [
            "template_id",
            "time_taken_manually_execute_minutes",
            "time_taken_create_automation_minutes",
        ]
