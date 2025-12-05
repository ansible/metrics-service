# Automation Reports - Quick Start Guide

## ✅ System Status

The automation reports collection system is now **fully operational** and ready to use!

### What's Available

- **18 Collectors** in metrics-utility for AWX/Controller data extraction
- **14 Django Models** for storing automation reports data
- **1 Integration Task** (`collect_automation_reports`) in metrics-service
- **13 Database Tables** in metricsStorage.sqlite (ar_ prefix)
- **Dashboard Access** at http://localhost:8000/dashboard/

### Login Credentials

- **Username**: `admin`
- **Password**: `admin`
- **Dashboard URL**: http://localhost:8000/dashboard/
- **Login URL**: http://localhost:8000/login/

---

## 🚀 Quick Start

### 1. Access the Dashboard

1. Navigate to http://localhost:8000/login/
2. Log in with `admin` / `admin`
3. Go to http://localhost:8000/dashboard/
4. Under "Select Function", find **"collect_automation_reports"** in the **"Automation Reports"** category

### 2. Create a Collection Task

**Basic Collection** (organizations, job templates, jobs, job host summaries):
```json
{
  "database": "awx"
}
```

**Jobs Only** (last 30 days):
```json
{
  "database": "awx",
  "collectors": ["jobs", "job_host_summaries"],
  "since": "2024-11-01T00:00:00Z",
  "until": "2024-12-01T00:00:00Z"
}
```

**Full Collection** (all entities):
```json
{
  "database": "awx",
  "collect_all_entities": true
}
```

### 3. Via API (Alternative)

```bash
# Create task via API
curl -X POST http://localhost:8000/api/v1/tasks/ \
  -H "Content-Type: application/json" \
  -H "Authorization: Token YOUR_TOKEN" \
  -d '{
    "name": "Collect Automation Reports",
    "function_name": "collect_automation_reports",
    "task_data": {
      "database": "awx",
      "collectors": ["organizations", "job_templates", "jobs", "job_host_summaries"]
    }
  }'
```

### 4. Via Django Shell

```python
from apps.tasks.tasks_automation_reports import collect_automation_reports

# Basic collection
result = collect_automation_reports(database='awx')

# Jobs only (date range)
result = collect_automation_reports(
    database='awx',
    collectors=['jobs', 'job_host_summaries'],
    since='2024-11-01T00:00:00Z',
    until='2024-12-01T00:00:00Z'
)

print(f"Collected {result['data']['results']['jobs']} jobs")
```

---

## 📊 Available Collectors

### Main Collectors (Default)
- `organizations` - AWX organizations
- `job_templates` - Job templates with ROI fields
- `jobs` - Job execution records
- `job_host_summaries` - Per-host execution stats

### Supporting Entities (Optional)
- `inventories` - AWX inventories
- `projects` - AWX projects
- `hosts` - Managed hosts
- `users` - AWX users
- `execution_environments` - Execution environments
- `instance_groups` - Instance groups
- `labels` - Labels

---

## 🗄️ Database Tables

All data is stored in **metricsStorage.sqlite** with `ar_` prefix:

| Table | Description |
|-------|-------------|
| `ar_organization` | Organizations |
| `ar_job_template` | Job templates + ROI fields |
| `ar_job` | Job execution records |
| `ar_job_host_summary` | Per-host execution stats |
| `ar_inventory` | Inventories |
| `ar_project` | Projects |
| `ar_host` | Hosts |
| `ar_user` | Users |
| `ar_execution_environment` | Execution environments |
| `ar_instance_group` | Instance groups |
| `ar_label` | Labels |
| `ar_job_label` | Job-Label relationships |
| `ar_collection_run` | Collection run metadata |

---

## 🔍 Querying Data

### Django ORM

```python
from apps.automation_reports.models import Job, Organization, JobTemplate

# Get all successful jobs
successful_jobs = Job.objects.using('metrics_storage').filter(
    status='successful'
).select_related('organization', 'job_template')

# Count jobs by organization
from django.db.models import Count, Avg, Sum

org_stats = Job.objects.using('metrics_storage').values(
    'organization__name'
).annotate(
    total_jobs=Count('id'),
    avg_duration=Avg('elapsed'),
    total_hosts=Sum('num_hosts')
).order_by('-total_jobs')
```

### SQLite Direct

```bash
sqlite3 metricsStorage.sqlite
```

```sql
-- Get jobs with organization and template
SELECT
    j.name,
    j.status,
    j.started,
    j.finished,
    j.elapsed,
    o.name as organization,
    jt.name as job_template
FROM ar_job j
LEFT JOIN ar_organization o ON j.organization_id = o.id
LEFT JOIN ar_job_template jt ON j.job_template_id = jt.id
WHERE j.finished >= datetime('now', '-30 days')
ORDER BY j.finished DESC
LIMIT 100;

-- Calculate ROI by template
SELECT
    jt.name as template_name,
    COUNT(j.id) as total_runs,
    (COUNT(j.id) * jt.time_taken_manually_execute_minutes) as time_saved_minutes,
    ((COUNT(j.id) * jt.time_taken_manually_execute_minutes - jt.time_taken_create_automation_minutes) /
     jt.time_taken_create_automation_minutes * 100) as roi_percentage
FROM ar_job_template jt
LEFT JOIN ar_job j ON j.job_template_id = jt.id AND j.status = 'successful'
GROUP BY jt.id, jt.name
HAVING total_runs > 0
ORDER BY roi_percentage DESC;
```

---

## 📖 Full Documentation

For comprehensive documentation, see:
- **AUTOMATION_REPORTS_COLLECTORS.md** - Complete usage guide with examples
- **AUTOMATION_REPORTS_IMPLEMENTATION.md** - Database schema and architecture

---

## ⚠️ Important Notes

1. **Collection Order Matters**: Organizations must be collected before job templates, which must be collected before jobs
2. **Foreign Keys**: Ensure related entities exist before collecting jobs (use `collect_all_entities: true` for first run)
3. **Date Ranges**: Use `since` and `until` parameters for large job collections to avoid memory issues
4. **Database Configuration**: Ensure AWX database is configured in Django settings under the name specified in `database` parameter

---

## 🎯 Next Steps

1. **Test Collection**: Run a basic collection to verify AWX database connectivity
2. **Schedule Regular Collection**: Set up recurring tasks for daily job collection
3. **Build Dashboard**: Create visualization for ROI metrics
4. **Export Data**: Set up automated reporting for stakeholders

---

## 🆘 Troubleshooting

**Problem**: "metrics-utility is not available"
- **Solution**: Ensure metrics-utility is installed in development mode: `pip install -e /path/to/metrics-utility`

**Problem**: "Organization not found for job template"
- **Solution**: Collect organizations before job templates, or use `collect_all_entities: true`

**Problem**: Task not visible in dashboard
- **Solution**: Ensure you're logged in (admin/admin) and developer mode is enabled

---

**System is ready to collect automation reports data!** 🚀
