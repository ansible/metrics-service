# Database Views - Quick Start Guide

## TL;DR

✅ **7 SQL views created** in `metricsStorage.sqlite`
✅ **Django models ready** to query them (`view_models.py`)
✅ **BI tools can use them** as regular tables
✅ **No migrations needed** - just SQL

---

## What Are Views?

Views are **saved SQL queries** that appear as tables to applications and BI tools.

**Key benefit**: Extract JSON data into queryable columns WITHOUT storing duplicates!

```sql
-- This view extracts JSON → columns
CREATE VIEW vw_config_metrics AS
SELECT
    json_extract(data, '$.controller_version') as controller_version,
    json_extract(data, '$.install_uuid') as install_uuid,
    -- ... more fields
FROM metric_data
WHERE metric_type = 'config';

-- Now query it like a table
SELECT * FROM vw_config_metrics WHERE controller_version >= '4.7';
```

---

## Quick Usage

### 1. Direct SQL (SQLite)

```bash
# Query views directly
sqlite3 metricsStorage.sqlite

sqlite> -- List all views
sqlite> SELECT name FROM sqlite_master WHERE type='view';

sqlite> -- Query config metrics
sqlite> SELECT controller_version, COUNT(*) as count
        FROM vw_config_metrics
        GROUP BY controller_version;

sqlite> -- Daily trends
sqlite> SELECT * FROM vw_metrics_daily_trends
        ORDER BY date DESC LIMIT 7;

sqlite> -- Top 10 modules
sqlite> SELECT * FROM vw_top_modules LIMIT 10;
```

### 2. Django ORM

```python
from apps.metrics_storage.view_models import ConfigMetricView, AnonymizedStatsView

# Query like any Django model
configs = ConfigMetricView.objects.using('metrics_storage').all()

# Filter
version_47 = ConfigMetricView.objects.using('metrics_storage').filter(
    controller_version__startswith='4.7'
)

# Aggregate
from django.db.models import Avg
avg_hosts = AnonymizedStatsView.objects.using('metrics_storage').aggregate(
    Avg('hosts_automated_total')
)
```

### 3. BI Tools

**Connect any BI tool to `metricsStorage.sqlite`:**

- **Tableau**: Data Source → SQLite → metricsStorage.sqlite
- **Power BI**: Get Data → SQLite → select views
- **Metabase**: Add Database → SQLite → views appear as tables
- **Grafana**: SQLite plugin → query views

Views appear as regular tables to all BI tools!

---

## Available Views

### Core Views

| View Name | Purpose | Key Fields |
|-----------|---------|------------|
| `vw_config_metrics` | Configuration data | controller_version, license_type, install_uuid |
| `vw_anonymized_stats` | Aggregate statistics | hosts_automated_total, jobs_total, modules_used_total |
| `vw_module_usage` | Module usage details | module_name, usage_count |
| `vw_collection_usage` | Collection usage | collection_name, usage_count |
| `vw_metrics_combined` | Config + Stats joined | All fields + license_utilization_percent |
| `vw_metrics_daily_trends` | Daily aggregates | date, avg_hosts_automated, avg_jobs_total |
| `vw_top_modules` | Most used modules | module_name, total_usage, collections_count |

### View Details

#### `vw_config_metrics`
Extracts config collector JSON into 25+ queryable columns:
- Controller info: version, URL, UUIDs
- Platform: system, release, type
- License: type, expiry, instances, validity
- Subscription: ID, name, SKU, account

#### `vw_anonymized_stats`
Extracts anonymized_rollups statistics:
- Automation: hosts_automated_total, jobs_total
- Modules: modules_used_total, avg_modules_per_playbook
- Execution Environments: ee_total, ee_custom_total

#### `vw_metrics_combined`
Joins config + stats with calculated fields:
- All config fields
- All stats fields
- **Calculated**: `license_utilization_percent`

#### `vw_metrics_daily_trends`
Daily aggregates across all metrics:
- Averages: avg_hosts_automated, avg_jobs_total
- Totals: total_hosts_automated, total_jobs
- License compliance counts

---

## Common Queries

### License Compliance

```sql
-- Find invalid licenses
SELECT
    controller_version,
    license_type,
    COUNT(*) as count
FROM vw_config_metrics
WHERE valid_license_key = 0
GROUP BY controller_version, license_type;
```

```python
# Django ORM
from apps.metrics_storage.view_models import ConfigMetricView

invalid = ConfigMetricView.objects.using('metrics_storage').filter(
    valid_license_key=False
).values('controller_version', 'license_type').annotate(
    count=Count('metric_id')
)
```

### Usage Trends

```sql
-- Last 30 days automation trends
SELECT
    date,
    avg_hosts_automated,
    avg_jobs_total,
    collections_count
FROM vw_metrics_daily_trends
WHERE date >= date('now', '-30 days')
ORDER BY date DESC;
```

```python
# Django ORM
from datetime import timedelta
from django.utils import timezone
from apps.metrics_storage.view_models import MetricsDailyTrendsView

thirty_days_ago = timezone.now().date() - timedelta(days=30)
trends = MetricsDailyTrendsView.objects.using('metrics_storage').filter(
    date__gte=thirty_days_ago
).order_by('-date')
```

### Top Modules

```sql
-- Top 10 most used modules
SELECT
    module_name,
    total_usage,
    collections_count,
    avg_usage_per_collection
FROM vw_top_modules
LIMIT 10;
```

```python
# Django ORM
from apps.metrics_storage.view_models import TopModulesView

top_10 = TopModulesView.objects.using('metrics_storage').all()[:10]
for module in top_10:
    print(f"{module.module_name}: {module.total_usage} uses")
```

### License Utilization

```sql
-- Controllers with high license utilization
SELECT
    controller_version,
    install_uuid,
    license_utilization_percent,
    hosts_automated_total,
    total_licensed_instances
FROM vw_metrics_combined
WHERE license_utilization_percent > 80
ORDER BY license_utilization_percent DESC;
```

---

## Files Created

### 1. SQL View Definitions
**`apps/metrics_storage/sql/create_views.sql`**
- Creates all 7 views
- Includes indexes for performance
- Contains usage examples

**Already executed** - views exist in metricsStorage.sqlite

### 2. Django Models for Views
**`apps/metrics_storage/view_models.py`**
- Django ORM models for each view
- `managed=False` (Django won't modify them)
- Includes usage examples

### 3. Documentation
**`docs/using-views-with-bi-tools.md`** - Comprehensive guide
**`docs/json-vs-normalized-metrics.md`** - Comparison guide
**`docs/VIEWS_QUICK_START.md`** - This file

---

## Testing Views

### Test in SQLite

```bash
# 1. Verify views exist
sqlite3 metricsStorage.sqlite "SELECT name FROM sqlite_master WHERE type='view';"

# 2. Test a query
sqlite3 metricsStorage.sqlite "SELECT * FROM vw_config_metrics LIMIT 1;"

# 3. Test aggregation
sqlite3 metricsStorage.sqlite "
SELECT
    controller_version,
    COUNT(*) as count
FROM vw_config_metrics
GROUP BY controller_version;
"
```

### Test with Django

```python
# Start shell
python manage.py shell

# Import view models
from apps.metrics_storage.view_models import *

# Test query
configs = ConfigMetricView.objects.using('metrics_storage').all()
print(f"Total configs: {configs.count()}")

# Test filter
version_47 = ConfigMetricView.objects.using('metrics_storage').filter(
    controller_version__startswith='4.7'
)
print(f"Version 4.7+: {version_47.count()}")

# Test aggregation
from django.db.models import Avg
avg_hosts = AnonymizedStatsView.objects.using('metrics_storage').aggregate(
    Avg('hosts_automated_total')
)
print(f"Average hosts: {avg_hosts}")
```

---

## Maintaining Views

### Recreating Views

If you need to change a view:

```bash
# 1. Edit apps/metrics_storage/sql/create_views.sql

# 2. Drop and recreate
sqlite3 metricsStorage.sqlite "DROP VIEW IF EXISTS vw_config_metrics;"
sqlite3 metricsStorage.sqlite < apps/metrics_storage/sql/create_views.sql

# Or recreate all views
sqlite3 metricsStorage.sqlite < apps/metrics_storage/sql/create_views.sql
```

### Adding New Views

```sql
-- 1. Add to create_views.sql
CREATE VIEW IF NOT EXISTS vw_my_new_view AS
SELECT
    json_extract(data, '$.my_field') as my_field,
    -- ... more fields
FROM metric_data
WHERE ...;

-- 2. Create corresponding Django model in view_models.py
class MyNewView(models.Model):
    my_field = models.CharField(max_length=100)

    class Meta:
        managed = False
        db_table = 'vw_my_new_view'
```

---

## Performance Tips

### 1. Indexes Already Created

```sql
-- Indexes on JSON extracts for common queries
CREATE INDEX idx_config_version
ON metric_data(json_extract(data, '$.controller_version'));

CREATE INDEX idx_hosts_automated
ON metric_data(json_extract(data, '$.statistics.hosts_automated_total'));
```

### 2. Query Plan Analysis

```sql
-- Check how SQLite executes a view query
EXPLAIN QUERY PLAN
SELECT * FROM vw_config_metrics
WHERE controller_version >= '4.7';
```

### 3. View Complexity

- ✅ Simple views are fast (single table, few JSON extracts)
- ⚠️ Complex joins may be slower
- ⚠️ Array flattening (`json_each`) can be expensive on large arrays

**Current views are optimized** - tested with good performance!

---

## When to Use Views vs Tables

### Use Views (Current approach) ✅

- ✅ POC/MVP (where you are now)
- ✅ Rapidly changing schemas
- ✅ Read-heavy workloads
- ✅ Want flexibility
- ✅ BI tool integration

### Use Normalized Tables

- Heavy write workloads (rare for metrics)
- Views become too slow (rare)
- Need foreign keys for data integrity

**For your use case, views are perfect!** 🎯

---

## Summary

### What You Have

- ✅ **7 queryable views** in metricsStorage.sqlite
- ✅ **Django ORM models** to query them
- ✅ **Indexes** for performance
- ✅ **BI-ready** - connect any tool

### What You Can Do

1. **Connect BI tools** → Query views as tables
2. **Use Django ORM** → Query with Python
3. **Direct SQL** → Maximum flexibility
4. **Build dashboards** → Views power your UI

### Next Steps

1. **Test with your BI tool** - Connect to metricsStorage.sqlite
2. **Run example queries** - See the power of views
3. **Build visualizations** - Use view data in charts
4. **Iterate** - Drop/recreate views as needs change

**Views give you the best of both worlds: JSON flexibility + table queryability!** 🚀

---

## Quick Reference Commands

```bash
# List views
sqlite3 metricsStorage.sqlite "SELECT name FROM sqlite_master WHERE type='view';"

# Query a view
sqlite3 metricsStorage.sqlite "SELECT * FROM vw_config_metrics LIMIT 5;"

# Recreate all views
sqlite3 metricsStorage.sqlite < apps/metrics_storage/sql/create_views.sql

# Test with Django
python manage.py shell
>>> from apps.metrics_storage.view_models import ConfigMetricView
>>> ConfigMetricView.objects.using('metrics_storage').all()
```
