# Using Database Views with BI Tools and UI

## Overview

**Database views** provide a SQL-based abstraction layer that makes your JSON metrics data queryable as regular database tables. This is perfect for BI tools!

### Why Views are Great for BI

✅ **BI tools see them as regular tables** - No special JSON handling needed
✅ **No schema changes** - Just SQL, no migrations required
✅ **Easy to iterate** - Drop and recreate views instantly
✅ **Performance** - Can be indexed and optimized
✅ **Django compatible** - Use with ORM or raw SQL

---

## What We Created

### 7 Views Available

1. **`vw_config_metrics`** - Flattened configuration data
2. **`vw_anonymized_stats`** - Aggregate statistics
3. **`vw_module_usage`** - Module usage details
4. **`vw_collection_usage`** - Collection usage details
5. **`vw_metrics_combined`** - Config + stats joined
6. **`vw_metrics_daily_trends`** - Daily aggregates
7. **`vw_top_modules`** - Most used modules

### How to Use Them

```sql
-- Views are already created in metricsStorage.sqlite
-- Just query them like normal tables

-- List all views
SELECT name FROM sqlite_master WHERE type='view';

-- Query a view
SELECT * FROM vw_config_metrics WHERE controller_version >= '4.7';
```

---

## BI Tool Integration

### Option 1: Direct SQLite Connection

Most BI tools can connect directly to SQLite databases.

#### **Tableau**
```
1. Data Source → SQLite
2. File: /path/to/metricsStorage.sqlite
3. Select view: vw_config_metrics
4. Create visualizations
```

#### **Power BI**
```
1. Get Data → Database → SQLite
2. File path: metricsStorage.sqlite
3. Navigator: Select views
4. Load data
```

#### **Metabase**
```
1. Add Database → SQLite
2. Database file: metricsStorage.sqlite
3. Views appear as tables
4. Create dashboards
```

#### **Grafana** (with SQLite plugin)
```
1. Add Data Source → SQLite
2. Path: metricsStorage.sqlite
3. Query views for time-series charts
```

### Option 2: REST API Access (Django)

Query views through Django REST Framework endpoints.

#### Create ViewSet for Views

```python
# apps/api/v1/metrics_data/views.py

from apps.metrics_storage.view_models import (
    ConfigMetricView,
    AnonymizedStatsView,
    MetricsCombinedView,
    MetricsDailyTrendsView,
    TopModulesView
)

class ConfigMetricViewSet(viewsets.ReadOnlyModelViewSet):
    """
    BI endpoint for config metrics view.

    Provides flattened, queryable config data extracted from JSON.
    """
    queryset = ConfigMetricView.objects.using('metrics_storage').all()
    serializer_class = ConfigMetricViewSerializer
    permission_classes = [AllowAny]  # POC
    pagination_class = MetricDataCursorPagination

    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = {
        'controller_version': ['exact', 'icontains', 'gte', 'lte'],
        'install_uuid': ['exact'],
        'license_type': ['exact', 'icontains'],
        'valid_license_key': ['exact'],
        'total_licensed_instances': ['gte', 'lte', 'exact'],
        'collected_at': ['gte', 'lte', 'exact'],
    }
    search_fields = ['controller_version', 'install_uuid', 'license_type']
    ordering_fields = ['collected_at', 'controller_version', 'total_licensed_instances']


class AnonymizedStatsViewSet(viewsets.ReadOnlyModelViewSet):
    """BI endpoint for anonymized stats view."""
    queryset = AnonymizedStatsView.objects.using('metrics_storage').all()
    serializer_class = AnonymizedStatsViewSerializer
    permission_classes = [AllowAny]  # POC

    filterset_fields = {
        'hosts_automated_total': ['gte', 'lte', 'exact'],
        'jobs_total': ['gte', 'lte', 'exact'],
        'modules_used_total': ['gte', 'lte'],
    }


class MetricsCombinedViewSet(viewsets.ReadOnlyModelViewSet):
    """BI endpoint for combined metrics view."""
    queryset = MetricsCombinedView.objects.using('metrics_storage').all()
    serializer_class = MetricsCombinedViewSerializer
    permission_classes = [AllowAny]  # POC

    filterset_fields = {
        'controller_version': ['exact', 'icontains'],
        'license_utilization_percent': ['gte', 'lte'],
        'valid_license_key': ['exact'],
    }


class DailyTrendsViewSet(viewsets.ReadOnlyModelViewSet):
    """BI endpoint for daily trends view."""
    queryset = MetricsDailyTrendsView.objects.using('metrics_storage').all()
    serializer_class = DailyTrendsViewSerializer
    permission_classes = [AllowAny]  # POC

    filterset_fields = {
        'date': ['gte', 'lte', 'exact'],
        'collections_count': ['gte'],
    }


class TopModulesViewSet(viewsets.ReadOnlyModelViewSet):
    """BI endpoint for top modules view."""
    queryset = TopModulesView.objects.using('metrics_storage').all()
    serializer_class = TopModulesViewSerializer
    permission_classes = [AllowAny]  # POC
    pagination_class = None  # Return all results
```

#### Register URLs

```python
# apps/api/v1/metrics_data/urls.py

router.register(r'views/config', ConfigMetricViewSet, basename='view-config')
router.register(r'views/stats', AnonymizedStatsViewSet, basename='view-stats')
router.register(r'views/combined', MetricsCombinedViewSet, basename='view-combined')
router.register(r'views/trends', DailyTrendsViewSet, basename='view-trends')
router.register(r'views/top-modules', TopModulesViewSet, basename='view-top-modules')
```

#### API Usage

```bash
# Query config metrics view
curl "http://localhost:8000/api/v1/metrics-data/views/config/"

# Filter by version
curl "http://localhost:8000/api/v1/metrics-data/views/config/?controller_version__gte=4.7"

# Find invalid licenses
curl "http://localhost:8000/api/v1/metrics-data/views/config/?valid_license_key=false"

# Get anonymized stats
curl "http://localhost:8000/api/v1/metrics-data/views/stats/"

# Filter by host count
curl "http://localhost:8000/api/v1/metrics-data/views/stats/?hosts_automated_total__gte=100"

# Get combined metrics
curl "http://localhost:8000/api/v1/metrics-data/views/combined/"

# Get daily trends for last 30 days
curl "http://localhost:8000/api/v1/metrics-data/views/trends/?date__gte=2024-11-01"

# Get top 10 modules
curl "http://localhost:8000/api/v1/metrics-data/views/top-modules/"
```

---

## Example BI Queries

### 1. License Compliance Dashboard

```sql
-- Controllers with invalid licenses
SELECT
    controller_version,
    license_type,
    COUNT(*) as count
FROM vw_config_metrics
WHERE valid_license_key = 0
GROUP BY controller_version, license_type
ORDER BY count DESC;
```

### 2. Usage Trends Over Time

```sql
-- Daily automation trends
SELECT
    date,
    avg_hosts_automated,
    avg_jobs_total,
    collections_count
FROM vw_metrics_daily_trends
WHERE date >= date('now', '-30 days')
ORDER BY date DESC;
```

### 3. Top Automated Modules

```sql
-- Most used modules across all collections
SELECT
    module_name,
    total_usage,
    collections_count,
    avg_usage_per_collection
FROM vw_top_modules
LIMIT 10;
```

### 4. License Utilization Analysis

```sql
-- Controllers by license utilization
SELECT
    controller_version,
    ROUND(AVG(license_utilization_percent), 2) as avg_utilization,
    COUNT(*) as instances
FROM vw_metrics_combined
WHERE license_utilization_percent IS NOT NULL
GROUP BY controller_version
HAVING instances >= 5
ORDER BY avg_utilization DESC;
```

### 5. Platform Distribution

```sql
-- Controllers by platform
SELECT
    platform_system,
    COUNT(*) as count,
    COUNT(DISTINCT install_uuid) as unique_installs
FROM vw_config_metrics
GROUP BY platform_system
ORDER BY count DESC;
```

### 6. Execution Environment Usage

```sql
-- EE adoption trends
SELECT
    DATE(collected_at) as date,
    AVG(ee_total) as avg_total_ee,
    AVG(ee_custom_total) as avg_custom_ee,
    AVG(CAST(ee_custom_total AS REAL) / NULLIF(ee_total, 0) * 100) as custom_percentage
FROM vw_anonymized_stats
WHERE ee_total > 0
GROUP BY DATE(collected_at)
ORDER BY date DESC;
```

---

## Performance Optimization

### 1. Index JSON Extract Paths

Already created in create_views.sql:

```sql
-- Index on controller_version
CREATE INDEX idx_config_version
ON metric_data(json_extract(data, '$.controller_version'));

-- Index on hosts_automated_total
CREATE INDEX idx_hosts_automated
ON metric_data(json_extract(data, '$.statistics.hosts_automated_total'));
```

### 2. View Query Plans

```sql
-- Check query plan for a view query
EXPLAIN QUERY PLAN
SELECT * FROM vw_config_metrics
WHERE controller_version >= '4.7';
```

### 3. Materialized Views (Manual Refresh)

SQLite doesn't have true materialized views, but you can create tables:

```sql
-- Create a "materialized" view as a table
CREATE TABLE mv_daily_summary AS
SELECT * FROM vw_metrics_daily_trends;

-- Refresh it (drop and recreate)
DROP TABLE mv_daily_summary;
CREATE TABLE mv_daily_summary AS
SELECT * FROM vw_metrics_daily_trends;
```

---

## UI Dashboard Integration

### Example: React Dashboard Component

```javascript
// Fetch daily trends from view endpoint
const DailyTrendsChart = () => {
  const [trends, setTrends] = useState([]);

  useEffect(() => {
    fetch('/api/v1/metrics-data/views/trends/?date__gte=2024-11-01')
      .then(res => res.json())
      .then(data => setTrends(data.results));
  }, []);

  return (
    <LineChart data={trends}>
      <Line dataKey="avg_hosts_automated" stroke="#8884d8" />
      <Line dataKey="avg_jobs_total" stroke="#82ca9d" />
    </LineChart>
  );
};
```

### Example: Django Template

```html
<!-- Load config metrics from view -->
{% load static %}

<table>
  <thead>
    <tr>
      <th>Controller Version</th>
      <th>Install UUID</th>
      <th>License Type</th>
      <th>Licensed Instances</th>
      <th>Valid</th>
    </tr>
  </thead>
  <tbody>
    {% for config in config_metrics %}
    <tr>
      <td>{{ config.controller_version }}</td>
      <td>{{ config.install_uuid }}</td>
      <td>{{ config.license_type }}</td>
      <td>{{ config.total_licensed_instances }}</td>
      <td>
        {% if config.valid_license_key %}
          <span class="badge-success">Valid</span>
        {% else %}
          <span class="badge-danger">Invalid</span>
        {% endif %}
      </td>
    </tr>
    {% endfor %}
  </tbody>
</table>
```

---

## Comparison: Views vs Normalized Tables

| Feature | Views | Normalized Tables |
|---------|-------|-------------------|
| **Schema Changes** | ✅ None (just SQL) | ❌ Require migrations |
| **Storage** | ✅ No duplication | ⚠️ Data duplicated |
| **Performance** | ⚠️ Computed on query | ✅ Pre-computed |
| **Flexibility** | ✅ Very flexible | ⚠️ Schema locked |
| **BI Support** | ✅ Excellent | ✅ Excellent |
| **Maintenance** | ✅ Easy (DROP/CREATE) | ⚠️ Medium (migrations) |
| **Write Speed** | ✅ Fast (no extra writes) | ⚠️ Slower (multiple inserts) |

### When to Use Each

**Use Views** (Current recommendation):
- ✅ POC/MVP stage
- ✅ Rapidly evolving schemas
- ✅ Read-heavy workloads
- ✅ Want flexibility

**Use Normalized Tables**:
- When views are too slow (rare)
- When you need write-optimized lookups
- When schema is 100% stable

---

## Testing the Views

### Django Shell Testing

```python
# Start Django shell
python manage.py shell

# Import view models
from apps.metrics_storage.view_models import *

# Query config metrics
configs = ConfigMetricView.objects.using('metrics_storage').all()[:5]
for c in configs:
    print(f"{c.controller_version} - {c.install_uuid}")

# Filter
invalid_licenses = ConfigMetricView.objects.using('metrics_storage').filter(
    valid_license_key=False
)
print(f"Invalid licenses: {invalid_licenses.count()}")

# Aggregate
from django.db.models import Avg
stats = AnonymizedStatsView.objects.using('metrics_storage').aggregate(
    avg_hosts=Avg('hosts_automated_total'),
    avg_jobs=Avg('jobs_total')
)
print(f"Average hosts: {stats['avg_hosts']}")
print(f"Average jobs: {stats['avg_jobs']}")

# Daily trends
from datetime import timedelta
from django.utils import timezone

thirty_days_ago = timezone.now().date() - timedelta(days=30)
trends = MetricsDailyTrendsView.objects.using('metrics_storage').filter(
    date__gte=thirty_days_ago
)
for t in trends:
    print(f"{t.date}: {t.avg_hosts_automated} hosts, {t.avg_jobs_total} jobs")

# Top modules
top_modules = TopModulesView.objects.using('metrics_storage').all()[:10]
for m in top_modules:
    print(f"{m.module_name}: {m.total_usage} uses")
```

### Direct SQL Testing

```bash
# Test views directly
sqlite3 metricsStorage.sqlite

# Config metrics
sqlite> SELECT controller_version, COUNT(*) as count
        FROM vw_config_metrics
        GROUP BY controller_version;

# Trends
sqlite> SELECT * FROM vw_metrics_daily_trends
        ORDER BY date DESC LIMIT 7;

# Top modules
sqlite> SELECT * FROM vw_top_modules LIMIT 10;
```

---

## Summary

### ✅ Views are Perfect For:

1. **BI Tools** - They see views as regular tables
2. **Reporting** - Pre-aggregated, fast queries
3. **Flexibility** - Change views without migrations
4. **UI Dashboards** - Queryable through Django ORM
5. **Analytics** - Complex queries on flattened data

### 📊 What You Have Now:

- ✅ 7 views created in SQLite
- ✅ Django models to query them (`view_models.py`)
- ✅ SQL definitions (`create_views.sql`)
- ✅ Indexes for performance
- ✅ Examples for BI tools and APIs

### 🚀 Next Steps:

1. **Test views with your BI tool** - Connect to metricsStorage.sqlite
2. **Create API endpoints** (optional) - Expose views via REST
3. **Build dashboards** - Use views for analytics
4. **Iterate** - Drop/recreate views as needs evolve

**Views give you all the benefits of normalized tables without the migration overhead!** 🎯
