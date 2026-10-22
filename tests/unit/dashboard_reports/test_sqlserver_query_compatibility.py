"""Compile dashboard queries with the SQL Server Django backend without connecting."""

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.conf import settings
from mssql.base import DatabaseWrapper

from apps.dashboard_reports.models import JobData, SubscriptionCost
from apps.dashboard_reports.viewsets import dashboard_leaderboards, dashboard_report


def _sql_server_connection():
    connection = DatabaseWrapper(
        {
            "ENGINE": "mssql",
            "NAME": "metrics_service",
            "HOST": "127.0.0.1",
            "PORT": "1433",
            "USER": "test-user",
            "PASSWORD": "test-password",
            "OPTIONS": {"driver": "ODBC Driver 18 for SQL Server"},
            "TIME_ZONE": settings.TIME_ZONE,
            "CONN_MAX_AGE": 0,
        },
        alias="sqlserver",
    )
    # The backend normally probes SQL Server for its version; query compilation
    # only needs a supported version value and must not open a DB connection.
    connection.__dict__["sql_server_version"] = 2022
    return connection


def test_latest_username_query_compiles_for_sql_server():
    queryset = dashboard_leaderboards._latest_usernames_queryset(JobData.objects.all(), {1, 2})
    sql, _ = queryset.query.get_compiler(connection=_sql_server_connection()).as_sql()

    assert "DISTINCT ON" not in sql
    assert "SELECT DISTINCT" in sql
    assert "SELECT TOP 1" in sql


def test_chart_aggregation_query_compiles_for_sql_server():
    queryset = dashboard_report._chart_bucket_queryset(JobData.objects.all(), "day")
    sql, _ = queryset.query.get_compiler(connection=_sql_server_connection()).as_sql()

    assert "GROUP BY" in sql
    assert "COUNT" in sql
    assert "SUM(" in sql
    assert "generate_series" not in sql


def test_aggregated_costs_use_fixed_point_decimal_parameters_for_sql_server():
    view = dashboard_report.DashboardReportViewSet()
    view.kwargs = {
        "start_date": datetime(2026, 10, 1, tzinfo=UTC),
        "end_date": datetime(2026, 10, 9, tzinfo=UTC),
    }
    subscription_cost = SimpleNamespace(
        cost_employee_per_minute=Decimal("1.00"),
        include_template_creation_time_in_costs=True,
        per_second_subscription_cost=lambda start, end: Decimal("0E-10"),
    )

    with patch.object(SubscriptionCost, "get", return_value=subscription_cost):
        queryset = view._build_aggregated_queryset(JobData.objects.all())
        _, params = queryset.query.get_compiler(connection=_sql_server_connection()).as_sql()

    assert "0.0000000000" in params
    assert "0E-10" not in params


def test_chart_time_buckets_include_the_end_bucket():
    start = datetime(2026, 3, 11, 0, 0, tzinfo=UTC)
    end = datetime(2026, 3, 13, 0, 0, tzinfo=UTC)

    assert dashboard_report._chart_time_buckets(start, end, "day") == [
        start,
        datetime(2026, 3, 12, 0, 0, tzinfo=UTC),
        end,
    ]


def test_chart_result_zero_fills_missing_buckets_with_public_shape():
    from apps.dashboard_reports.viewsets.dashboard_report import DashboardReportViewSet

    start = datetime(2026, 3, 11, 0, 0, tzinfo=UTC)
    end = datetime(2026, 3, 12, 0, 0, tzinfo=UTC)
    result = DashboardReportViewSet()._format_chart_result([start, end], {start: (2, 9)}, "day")

    assert result == {
        "job_chart": {"kind": "day", "items": [{"label": start, "value": 2}, {"label": end, "value": 0}]},
        "host_chart": {"kind": "day", "items": [{"label": start, "value": 9}, {"label": end, "value": 0}]},
    }


def test_get_chart_data_uses_grouped_rows_and_fills_the_next_bucket(monkeypatch):
    from apps.dashboard_reports.viewsets import dashboard_report

    start = datetime(2026, 3, 11, 0, 0, tzinfo=UTC)
    view = dashboard_report.DashboardReportViewSet()
    view.kwargs = {"start_date": start, "end_date": start}
    monkeypatch.setattr(view, "_filter_raw_jobdata_queryset", lambda queryset: queryset)
    monkeypatch.setattr(
        dashboard_report,
        "_chart_bucket_queryset",
        lambda queryset, kind: [{"term": start, "runs": 2, "hosts": 9}],
    )

    result = view.get_chart_data()

    assert result["job_chart"]["kind"] == "hour"
    assert result["job_chart"]["items"] == [
        {"label": start, "value": 2},
        {"label": datetime(2026, 3, 11, 1, 0, tzinfo=UTC), "value": 0},
    ]
