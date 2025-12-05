"""
Django models for SQLite views.

These models allow you to query the database views as if they were regular models.
They use managed=False so Django doesn't try to create/modify the underlying views.

Usage:
    from apps.metrics_storage.view_models import ConfigMetricView

    # Query like any Django model
    recent_configs = ConfigMetricView.objects.all()[:10]

    # Filter
    version_47 = ConfigMetricView.objects.filter(controller_version__startswith='4.7')

    # Aggregate
    from django.db.models import Avg
    avg_hosts = AnonymizedStatsView.objects.aggregate(Avg('hosts_automated_total'))
"""

from django.db import models


class ConfigMetricView(models.Model):
    """
    Django model for vw_config_metrics view.

    Provides queryable access to configuration metrics extracted from JSON.
    """

    metric_id = models.IntegerField(primary_key=True)
    collected_at = models.DateTimeField()
    collection_run_id = models.IntegerField()
    collection_started_at = models.DateTimeField()
    collection_status = models.CharField(max_length=20)

    # Controller information
    controller_version = models.CharField(max_length=50)
    controller_url = models.CharField(max_length=500)
    install_uuid = models.CharField(max_length=100)
    instance_uuid = models.CharField(max_length=100, null=True)

    # Platform information
    platform_system = models.CharField(max_length=50)
    platform_release = models.CharField(max_length=100)
    platform_type = models.CharField(max_length=50)

    # License information
    license_type = models.CharField(max_length=100, null=True)
    license_date = models.DateField(null=True)
    license_expiry_days = models.IntegerField(null=True)
    total_licensed_instances = models.IntegerField(null=True)
    free_instances = models.IntegerField(null=True)
    current_instances = models.IntegerField(null=True)
    valid_license_key = models.BooleanField()

    # Subscription information
    subscription_id = models.CharField(max_length=200, null=True)
    subscription_name = models.CharField(max_length=200, null=True)
    subscription_usage_model = models.CharField(max_length=100, null=True)
    sku = models.CharField(max_length=100, null=True)
    account_number = models.CharField(max_length=100, null=True)

    # Versions
    metrics_utility_version = models.CharField(max_length=50, null=True)

    # Flags
    is_trial = models.BooleanField(null=True)
    is_compliant = models.BooleanField(null=True)

    class Meta:
        managed = False  # Django won't try to create this table
        db_table = "vw_config_metrics"
        ordering = ["-collected_at"]


class AnonymizedStatsView(models.Model):
    """
    Django model for vw_anonymized_stats view.

    Provides queryable access to anonymized statistics.
    """

    metric_id = models.IntegerField(primary_key=True)
    collected_at = models.DateTimeField()
    collection_run_id = models.IntegerField()
    collection_started_at = models.DateTimeField()

    # Core statistics
    modules_used_total = models.IntegerField(null=True)
    avg_modules_per_playbook = models.FloatField(null=True)
    hosts_automated_total = models.IntegerField(null=True)
    event_total = models.IntegerField(null=True)
    jobs_total = models.IntegerField(null=True)
    unique_hosts_total = models.IntegerField(null=True)
    job_host_summary_total = models.IntegerField(null=True)

    # Execution Environment stats
    ee_total = models.IntegerField(null=True)
    ee_default_total = models.IntegerField(null=True)
    ee_custom_total = models.IntegerField(null=True)

    class Meta:
        managed = False
        db_table = "vw_anonymized_stats"
        ordering = ["-collected_at"]


class ModuleUsageView(models.Model):
    """
    Django model for vw_module_usage view.

    Flattened module usage data from anonymized rollups.
    """

    metric_id = models.IntegerField()
    collected_at = models.DateTimeField()
    collection_run_id = models.IntegerField()
    module_name = models.CharField(max_length=200)
    usage_count = models.IntegerField()

    class Meta:
        managed = False
        db_table = "vw_module_usage"
        ordering = ["-usage_count"]


class CollectionUsageView(models.Model):
    """
    Django model for vw_collection_usage view.

    Flattened collection usage data.
    """

    metric_id = models.IntegerField()
    collected_at = models.DateTimeField()
    collection_run_id = models.IntegerField()
    collection_name = models.CharField(max_length=200)
    usage_count = models.IntegerField()

    class Meta:
        managed = False
        db_table = "vw_collection_usage"
        ordering = ["-usage_count"]


class MetricsCombinedView(models.Model):
    """
    Django model for vw_metrics_combined view.

    Combines config and anonymized stats for comprehensive reporting.
    """

    collection_run_id = models.IntegerField(primary_key=True)
    collected_at = models.DateTimeField()

    # Controller info
    controller_version = models.CharField(max_length=50)
    install_uuid = models.CharField(max_length=100)
    platform_system = models.CharField(max_length=50)

    # License info
    license_type = models.CharField(max_length=100, null=True)
    total_licensed_instances = models.IntegerField(null=True)
    free_instances = models.IntegerField(null=True)
    valid_license_key = models.BooleanField()

    # Usage stats
    hosts_automated_total = models.IntegerField(null=True)
    jobs_total = models.IntegerField(null=True)
    modules_used_total = models.IntegerField(null=True)
    unique_hosts_total = models.IntegerField(null=True)
    ee_total = models.IntegerField(null=True)
    ee_custom_total = models.IntegerField(null=True)

    # Calculated fields
    license_utilization_percent = models.FloatField(null=True)

    class Meta:
        managed = False
        db_table = "vw_metrics_combined"
        ordering = ["-collected_at"]


class MetricsDailyTrendsView(models.Model):
    """
    Django model for vw_metrics_daily_trends view.

    Daily aggregated metrics for trending analysis.
    """

    date = models.DateField(primary_key=True)
    collections_count = models.IntegerField()

    # Averages
    avg_hosts_automated = models.FloatField(null=True)
    avg_jobs_total = models.FloatField(null=True)
    avg_licensed_instances = models.FloatField(null=True)

    # Totals
    total_hosts_automated = models.IntegerField(null=True)
    total_jobs = models.IntegerField(null=True)

    # License compliance
    valid_licenses_count = models.IntegerField()
    invalid_licenses_count = models.IntegerField()

    class Meta:
        managed = False
        db_table = "vw_metrics_daily_trends"
        ordering = ["-date"]


class TopModulesView(models.Model):
    """
    Django model for vw_top_modules view.

    Most used modules across all collections.
    """

    module_name = models.CharField(max_length=200, primary_key=True)
    total_usage = models.IntegerField()
    collections_count = models.IntegerField()
    avg_usage_per_collection = models.FloatField()
    max_usage = models.IntegerField()
    last_seen = models.DateTimeField()

    class Meta:
        managed = False
        db_table = "vw_top_modules"
        ordering = ["-total_usage"]


# ============================================================================
# USAGE EXAMPLES
# ============================================================================

"""
# 1. Query config metrics
from apps.metrics_storage.view_models import ConfigMetricView

# Get all configs
configs = ConfigMetricView.objects.using('metrics_storage').all()

# Filter by version
version_47 = ConfigMetricView.objects.using('metrics_storage').filter(
    controller_version__startswith='4.7'
)

# Find invalid licenses
invalid = ConfigMetricView.objects.using('metrics_storage').filter(
    valid_license_key=False
)


# 2. Query anonymized stats
from apps.metrics_storage.view_models import AnonymizedStatsView

# Get stats with lots of hosts
high_usage = AnonymizedStatsView.objects.using('metrics_storage').filter(
    hosts_automated_total__gt=100
)

# Calculate averages
from django.db.models import Avg
avg_hosts = AnonymizedStatsView.objects.using('metrics_storage').aggregate(
    Avg('hosts_automated_total')
)


# 3. Query combined metrics
from apps.metrics_storage.view_models import MetricsCombinedView

# Get combined view with high utilization
high_util = MetricsCombinedView.objects.using('metrics_storage').filter(
    license_utilization_percent__gt=80
).select_related()


# 4. Query daily trends
from apps.metrics_storage.view_models import MetricsDailyTrendsView
from datetime import timedelta
from django.utils import timezone

# Last 30 days
thirty_days_ago = timezone.now().date() - timedelta(days=30)
trends = MetricsDailyTrendsView.objects.using('metrics_storage').filter(
    date__gte=thirty_days_ago
)


# 5. Query top modules
from apps.metrics_storage.view_models import TopModulesView

# Top 10 modules
top_10 = TopModulesView.objects.using('metrics_storage').all()[:10]


# 6. Complex query with multiple views
# Find controllers with high usage and invalid licenses
from django.db.models import Q

problem_controllers = ConfigMetricView.objects.using('metrics_storage').filter(
    valid_license_key=False,
    total_licensed_instances__lt=100
).values('install_uuid', 'controller_version', 'license_type')


# 7. Use in API serializers
from rest_framework import serializers

class ConfigMetricViewSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConfigMetricView
        fields = '__all__'

# Then in views:
from rest_framework import viewsets

class ConfigMetricViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = ConfigMetricView.objects.using('metrics_storage').all()
    serializer_class = ConfigMetricViewSerializer
"""
