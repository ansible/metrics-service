"""
API views for metrics data endpoints.

Provides BI and UI optimized endpoints for accessing metrics data from SQLite.
POC VERSION: Unauthenticated access allowed for testing.
"""

from django.db.models import Avg, Count, Max, Min, Sum
from django.utils import timezone
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.pagination import CursorPagination
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from apps.metrics_storage.models import CollectionRun, MetricData, MetricType

from .serializers import (
    CollectionRunSerializer,
    MetricDataDetailSerializer,
    MetricDataSerializer,
    MetricTypeSerializer,
)


class MetricDataCursorPagination(CursorPagination):
    """
    Cursor-based pagination for BI endpoint.

    Optimized for large datasets with efficient forward/backward navigation.
    """

    page_size = 100
    page_size_query_param = "page_size"
    max_page_size = 1000
    ordering = "-collected_at"


class BIMetricDataViewSet(viewsets.ReadOnlyModelViewSet):
    """
    BI-optimized endpoint for metrics data export.

    This endpoint is designed for Business Intelligence tools to extract
    metrics data for analysis and reporting.

    ## Query Parameters:
    - `start_date`: ISO 8601 datetime (filter by collected_at >= start_date)
    - `end_date`: ISO 8601 datetime (filter by collected_at <= end_date)
    - `metric_type`: Metric type name (e.g., 'config', 'job_host_summary')
    - `was_successful`: Boolean (filter by success status)
    - `collection_run_id`: Integer (filter by specific collection run)
    - `page_size`: Records per page (default 100, max 1000)

    ## POC Note:
    This endpoint has unauthenticated access enabled for testing purposes.
    In production, implement proper authentication and authorization.
    """

    serializer_class = MetricDataSerializer
    pagination_class = MetricDataCursorPagination
    permission_classes = [AllowAny]  # POC: Unauthenticated access

    def get_queryset(self):
        """
        Get metrics data with optional filtering.

        Uses the metrics_storage database via database router.
        """
        queryset = MetricData.objects.using("metrics_storage").select_related("metric_type", "collection_run").all()

        # Filter by date range
        start_date = self.request.query_params.get("start_date")
        end_date = self.request.query_params.get("end_date")

        if start_date:
            queryset = queryset.filter(collected_at__gte=start_date)
        if end_date:
            queryset = queryset.filter(collected_at__lte=end_date)

        # Filter by metric type
        metric_type = self.request.query_params.get("metric_type")
        if metric_type:
            queryset = queryset.filter(metric_type__name=metric_type)

        # Filter by success status
        was_successful = self.request.query_params.get("was_successful")
        if was_successful is not None:
            queryset = queryset.filter(was_successful=was_successful.lower() == "true")

        # Filter by collection run
        collection_run_id = self.request.query_params.get("collection_run_id")
        if collection_run_id:
            queryset = queryset.filter(collection_run_id=collection_run_id)

        return queryset

    def retrieve(self, request, *args, **kwargs):
        """Get detailed view of a single metric data record."""
        instance = self.get_object()
        serializer = MetricDataDetailSerializer(instance)
        return Response(serializer.data)

    @action(detail=False, methods=["get"])
    def metric_types(self, request):
        """
        Get list of available metric types.

        Returns all metric types that have collected data.
        """
        metric_types = MetricType.objects.using("metrics_storage").filter(is_active=True).order_by("name")

        serializer = MetricTypeSerializer(metric_types, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["get"])
    def collection_runs(self, request):
        """
        Get list of collection runs.

        Query Parameters:
        - status: Filter by status (pending, running, completed, failed)
        - limit: Limit number of results (default 20)
        """
        queryset = CollectionRun.objects.using("metrics_storage").all()

        # Filter by status
        status_filter = request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        # Limit results
        limit = int(request.query_params.get("limit", 20))
        queryset = queryset[:limit]

        serializer = CollectionRunSerializer(queryset, many=True)
        return Response(serializer.data)


class UIMetricDataViewSet(viewsets.ViewSet):
    """
    UI-optimized endpoint with aggregations and summaries.

    This endpoint is designed for web dashboards and UI components,
    providing pre-aggregated data for fast rendering.

    ## POC Note:
    This endpoint has unauthenticated access enabled for testing purposes.
    """

    permission_classes = [AllowAny]  # POC: Unauthenticated access

    @action(detail=False, methods=["get"])
    def summary(self, request):
        """
        Get aggregated metrics summary.

        Query Parameters:
        - period: Time period (hour, day, week, month) - default: day
        - metric_type: Filter by specific metric type

        Returns aggregated statistics for the specified period.
        """
        period = request.query_params.get("period", "day")
        metric_type = request.query_params.get("metric_type")

        # Calculate time range
        now = timezone.now()
        period_map = {
            "hour": timezone.timedelta(hours=1),
            "day": timezone.timedelta(days=1),
            "week": timezone.timedelta(weeks=1),
            "month": timezone.timedelta(days=30),
        }
        start_time = now - period_map.get(period, timezone.timedelta(days=1))

        # Query metrics
        queryset = MetricData.objects.using("metrics_storage").filter(collected_at__gte=start_time)

        if metric_type:
            queryset = queryset.filter(metric_type__name=metric_type)

        # Aggregate statistics
        summary_stats = queryset.aggregate(
            total_metrics=Count("id"),
            successful_metrics=Count("id", filter=queryset.filter(was_successful=True).query),
            failed_metrics=Count("id", filter=queryset.filter(was_successful=False).query),
            avg_data_size=Avg("data_size_bytes"),
            max_data_size=Max("data_size_bytes"),
            min_data_size=Min("data_size_bytes"),
            total_data_size=Sum("data_size_bytes"),
        )

        # Get metric type distribution
        metric_type_distribution = queryset.values("metric_type__name").annotate(count=Count("id")).order_by("-count")

        return Response(
            {
                "period": period,
                "start_time": start_time,
                "end_time": now,
                "metric_type_filter": metric_type,
                "summary": summary_stats,
                "metric_type_distribution": list(metric_type_distribution),
            }
        )

    @action(detail=False, methods=["get"])
    def recent(self, request):
        """
        Get most recent metrics.

        Query Parameters:
        - limit: Number of records to return (default 100, max 500)
        - metric_type: Filter by specific metric type

        Returns the most recent metric data records.
        """
        limit = min(int(request.query_params.get("limit", 100)), 500)
        metric_type = request.query_params.get("metric_type")

        queryset = (
            MetricData.objects.using("metrics_storage")
            .select_related("metric_type", "collection_run")
            .order_by("-collected_at")
        )

        if metric_type:
            queryset = queryset.filter(metric_type__name=metric_type)

        queryset = queryset[:limit]

        serializer = MetricDataSerializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["get"])
    def stats(self, request):
        """
        Get overall statistics about the metrics database.

        Returns counts and statistics across all metrics.
        """
        total_metrics = MetricData.objects.using("metrics_storage").count()
        total_collection_runs = CollectionRun.objects.using("metrics_storage").count()
        total_metric_types = MetricType.objects.using("metrics_storage").filter(is_active=True).count()

        latest_collection = (
            CollectionRun.objects.using("metrics_storage").filter(status="completed").order_by("-completed_at").first()
        )

        latest_metric = MetricData.objects.using("metrics_storage").order_by("-collected_at").first()

        return Response(
            {
                "total_metrics": total_metrics,
                "total_collection_runs": total_collection_runs,
                "total_metric_types": total_metric_types,
                "latest_collection_run": CollectionRunSerializer(latest_collection).data if latest_collection else None,
                "latest_metric_collected_at": latest_metric.collected_at if latest_metric else None,
                "database_path": "metricsStorage.sqlite",
            }
        )
