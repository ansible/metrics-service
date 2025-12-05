"""
EXAMPLE: Normalized models for metrics data.

This shows how you could split out the JSON data into dedicated models
for better queryability. This is NOT currently enabled - just an example.

To use this approach:
1. Rename this file to models_config.py or similar
2. Import these models in models.py
3. Create and run migrations
4. Update collect_and_store_metrics to populate these models
"""

from django.db import models
from django.utils import timezone


class ConfigMetric(models.Model):
    """
    Normalized model for configuration metrics.

    Extracts key fields from the config collector's JSON data
    for easier querying and indexing.
    """

    # Link to parent MetricData
    metric_data = models.OneToOneField(
        "metrics_storage.MetricData", on_delete=models.CASCADE, related_name="config_detail"
    )

    # Controller information
    controller_url_base = models.URLField(max_length=500, null=True, blank=True)
    controller_version = models.CharField(max_length=50, null=True, blank=True, db_index=True)
    install_uuid = models.UUIDField(null=True, blank=True, db_index=True)
    instance_uuid = models.UUIDField(null=True, blank=True)

    # Platform information
    platform_system = models.CharField(max_length=50, null=True, blank=True)
    platform_release = models.CharField(max_length=100, null=True, blank=True)
    platform_type = models.CharField(max_length=50, null=True, blank=True)

    # License information
    license_type = models.CharField(max_length=100, null=True, blank=True, db_index=True)
    license_date = models.DateField(null=True, blank=True)
    license_expiry = models.IntegerField(null=True, blank=True)
    total_licensed_instances = models.IntegerField(null=True, blank=True)
    free_instances = models.IntegerField(default=0)
    current_instances = models.IntegerField(null=True, blank=True)
    valid_key = models.BooleanField(default=False, db_index=True)

    # Subscription information
    subscription_id = models.CharField(max_length=200, null=True, blank=True)
    subscription_name = models.CharField(max_length=200, null=True, blank=True)
    subscription_usage_model = models.CharField(max_length=100, null=True, blank=True)
    sku = models.CharField(max_length=100, null=True, blank=True)

    # Metrics utility version
    metrics_utility_version = models.CharField(max_length=50, null=True, blank=True)

    # Metadata
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "config_metrics"
        indexes = [
            models.Index(fields=["controller_version", "created_at"]),
            models.Index(fields=["license_type", "valid_key"]),
            models.Index(fields=["install_uuid"]),
        ]

    def __str__(self):
        return f"Config {self.controller_version} - {self.install_uuid}"

    @classmethod
    def create_from_json(cls, metric_data_instance, json_data):
        """
        Factory method to create ConfigMetric from JSON data.

        Usage:
            config_metric = ConfigMetric.create_from_json(metric_data, data)
        """
        platform_data = json_data.get("platform", {})

        return cls.objects.create(
            metric_data=metric_data_instance,
            controller_url_base=json_data.get("controller_url_base"),
            controller_version=json_data.get("controller_version"),
            install_uuid=json_data.get("install_uuid"),
            instance_uuid=json_data.get("instance_uuid"),
            platform_system=platform_data.get("system"),
            platform_release=platform_data.get("release"),
            platform_type=platform_data.get("type"),
            license_type=json_data.get("license_type"),
            license_date=json_data.get("license_date"),
            license_expiry=json_data.get("license_expiry"),
            total_licensed_instances=json_data.get("total_licensed_instances"),
            free_instances=json_data.get("free_instances", 0),
            current_instances=json_data.get("current_instances"),
            valid_key=json_data.get("valid_key", False),
            subscription_id=json_data.get("subscription_id"),
            subscription_name=json_data.get("subscription_name"),
            subscription_usage_model=json_data.get("subscription_usage_model"),
            sku=json_data.get("sku"),
            metrics_utility_version=json_data.get("metrics_utility_version"),
        )


class AnonymizedRollupsMetric(models.Model):
    """
    Normalized model for anonymized rollups statistics.

    Extracts aggregate statistics from anonymized_rollups collector.
    """

    # Link to parent MetricData
    metric_data = models.OneToOneField(
        "metrics_storage.MetricData", on_delete=models.CASCADE, related_name="anonymized_detail"
    )

    # Statistics from the statistics object
    modules_used_total = models.IntegerField(null=True, blank=True)
    avg_modules_per_playbook = models.FloatField(null=True, blank=True)
    hosts_automated_total = models.IntegerField(null=True, blank=True, db_index=True)
    event_total = models.IntegerField(default=0)
    jobs_total = models.IntegerField(null=True, blank=True, db_index=True)
    unique_hosts_total = models.IntegerField(null=True, blank=True)
    job_host_summary_total = models.IntegerField(default=0)

    # Execution environment stats
    ee_total = models.IntegerField(null=True, blank=True)
    ee_default_total = models.IntegerField(null=True, blank=True)
    ee_custom_total = models.IntegerField(null=True, blank=True)

    # Metadata
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "anonymized_rollups_metrics"
        indexes = [
            models.Index(fields=["hosts_automated_total", "jobs_total"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        return f"Anonymized Stats - {self.jobs_total} jobs, {self.hosts_automated_total} hosts"

    @classmethod
    def create_from_json(cls, metric_data_instance, json_data):
        """Factory method to create from JSON data."""
        stats = json_data.get("statistics", {})

        return cls.objects.create(
            metric_data=metric_data_instance,
            modules_used_total=stats.get("modules_used_to_automate_total"),
            avg_modules_per_playbook=stats.get("avg_number_of_modules_used_in_a_playbooks"),
            hosts_automated_total=stats.get("hosts_automated_total"),
            event_total=stats.get("event_total", 0),
            jobs_total=stats.get("jobs_total"),
            unique_hosts_total=stats.get("unique_hosts_total"),
            job_host_summary_total=stats.get("jobhostsummary_total", 0),
            ee_total=stats.get("EE_total"),
            ee_default_total=stats.get("EE_default_total"),
            ee_custom_total=stats.get("EE_custom_total"),
        )


class ModuleUsageMetric(models.Model):
    """
    Normalized model for module usage statistics.

    Each row represents one module's usage from the anonymized_rollups data.
    """

    # Link to parent anonymized metric
    anonymized_metric = models.ForeignKey(
        AnonymizedRollupsMetric, on_delete=models.CASCADE, related_name="module_usage"
    )

    # Module information
    module_name = models.CharField(max_length=200, db_index=True)
    collection_name = models.CharField(max_length=200, null=True, blank=True, db_index=True)

    # Usage statistics
    usage_count = models.IntegerField(default=0)
    playbook_count = models.IntegerField(default=0)

    class Meta:
        db_table = "module_usage_metrics"
        indexes = [
            models.Index(fields=["module_name", "-usage_count"]),
            models.Index(fields=["collection_name"]),
        ]

    def __str__(self):
        return f"{self.module_name} - {self.usage_count} uses"


# Example usage in collect_and_store_metrics task:
"""
# After saving MetricData, also save normalized data:

if metric_type.name == 'config' and was_successful:
    from apps.metrics_storage.models_normalized import ConfigMetric
    ConfigMetric.create_from_json(metric_data_obj, data_to_store)

elif metric_type.name == 'anonymized_rollups' and was_successful:
    from apps.metrics_storage.models_normalized import AnonymizedRollupsMetric, ModuleUsageMetric

    # Create main stats record
    anonymized = AnonymizedRollupsMetric.create_from_json(metric_data_obj, data_to_store)

    # Create module usage records
    for module_data in data_to_store.get('module_stats', []):
        ModuleUsageMetric.objects.create(
            anonymized_metric=anonymized,
            module_name=module_data.get('module'),
            usage_count=module_data.get('count', 0)
        )
"""

# Example queries you could run:
"""
# Find all configs with invalid licenses
invalid_licenses = ConfigMetric.objects.filter(valid_key=False)

# Get average hosts automated across all collections
from django.db.models import Avg
avg_hosts = AnonymizedRollupsMetric.objects.aggregate(Avg('hosts_automated_total'))

# Find most used modules
top_modules = ModuleUsageMetric.objects.order_by('-usage_count')[:10]

# Get configs by version
version_47 = ConfigMetric.objects.filter(controller_version__startswith='4.7')

# Complex query: Find all metrics where hosts > 100 and jobs > 50
metrics = AnonymizedRollupsMetric.objects.filter(
    hosts_automated_total__gt=100,
    jobs_total__gt=50
).select_related('metric_data', 'metric_data__collection_run')
"""
