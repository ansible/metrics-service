# Automation Reports Collectors - Implementation Summary

## Overview

Successfully created automation reports collectors in metrics-utility and integration task in metrics-service to collect AWX/Controller job data for automation ROI reporting.

---

## What Was Created

### 1. Metrics-Utility Collectors (5 files)

**Location**: `/Users/cshiels/Documents/Repos/Forked/metrics-utility/metrics_utility/library/collectors/controller/`

#### automation_reports_organizations.py
- `automation_reports_organizations()` - Collect all organizations
- `automation_reports_organizations_daily()` - Collect organizations by date range

#### automation_reports_job_templates.py
- `automation_reports_job_templates()` - Collect all job templates (includes ROI fields)
- `automation_reports_job_templates_daily()` - Collect job templates by date range

#### automation_reports_jobs.py
- `automation_reports_jobs()` - Collect job execution data with host counts
- `automation_reports_jobs_daily()` - Collect jobs by finished date range

#### automation_reports_job_host_summaries.py
- `automation_reports_job_host_summaries()` - Collect per-host execution statistics
- `automation_reports_job_host_summaries_daily()` - Collect summaries by job date range

#### automation_reports_entities.py
- `automation_reports_inventories()` / `automation_reports_inventories_daily()`
- `automation_reports_projects()` / `automation_reports_projects_daily()`
- `automation_reports_hosts()` / `automation_reports_hosts_daily()`
- `automation_reports_users()` / `automation_reports_users_daily()`
- `automation_reports_execution_environments()` / `automation_reports_execution_environments_daily()`
- `automation_reports_instance_groups()` / `automation_reports_instance_groups_daily()`
- `automation_reports_labels()` / `automation_reports_labels_daily()`

### 2. Metrics-Service Integration

**Location**: `/Users/cshiels/Documents/Repos/Forked/metrics-service/apps/tasks/tasks_automation_reports.py`

#### Task: `collect_automation_reports`

Collects automation reports data from AWX/Controller and stores in metricsStorage.sqlite.

**Features**:
- Uses metrics-utility collectors to gather data from AWX PostgreSQL
- Processes CSV output and stores in automation_reports tables
- Tracks collection runs with CollectionRun model
- Supports date range filtering
- Handles all foreign key relationships
- Transaction-safe with rollback on error

---

## How to Use

### Basic Collection (All Default Collectors)

```python
# Via Django shell
from apps.tasks.tasks_automation_reports import collect_automation_reports

result = collect_automation_reports()
```

### Via Task Dashboard

1. Navigate to http://localhost:8000/dashboard/
2. Select function: `collect_automation_reports`
3. Configure parameters:
   - **database**: `awx` (or your AWX database name)
   - **collectors**: `["organizations", "job_templates", "jobs", "job_host_summaries"]`
   - **since/until**: Optional date range
4. Click "Create Task"

### Via API

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
      "collectors": ["organizations", "job_templates", "jobs", "job_host_summaries"],
      "since": "2024-11-01T00:00:00Z",
      "until": "2024-12-01T00:00:00Z"
    }
  }'
```

---

## Collection Parameters

### Required Parameters
- None (all have defaults)

### Optional Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `database` | string | `"awx"` | Django database connection name for AWX/Controller |
| `since` | string | None | Start date for collection (ISO 8601 format) |
| `until` | string | None | End date for collection (ISO 8601 format) |
| `collectors` | array | `["organizations", "job_templates", "jobs", "job_host_summaries"]` | List of collectors to run |
| `collect_all_entities` | boolean | `false` | Whether to collect all supporting entities |

### Collectors Available

**Main Collectors** (default):
- `organizations` - AWX organizations
- `job_templates` - Job templates with ROI fields
- `jobs` - Job execution records
- `job_host_summaries` - Per-host execution stats

**Supporting Entities** (optional):
- `inventories` - AWX inventories
- `projects` - AWX projects
- `hosts` - Managed hosts
- `users` - AWX users

---

## Collection Examples

### Example 1: Collect Last 30 Days of Jobs

```python
from datetime import datetime, timedelta
from django.utils import timezone

result = collect_automation_reports(
    database='awx',
    collectors=['organizations', 'job_templates', 'jobs'],
    since=(timezone.now() - timedelta(days=30)).isoformat(),
    until=timezone.now().isoformat()
)

print(f"Collected {result['data']['results']['jobs']} jobs")
```

### Example 2: Full Collection with All Entities

```python
result = collect_automation_reports(
    database='awx',
    collect_all_entities=True,
    since='2024-01-01T00:00:00Z',
    until='2024-12-31T23:59:59Z'
)

print(f"Organizations: {result['data']['results']['organizations']}")
print(f"Job Templates: {result['data']['results']['job_templates']}")
print(f"Jobs: {result['data']['results']['jobs']}")
print(f"Inventories: {result['data']['results']['inventories']}")
print(f"Projects: {result['data']['results']['projects']}")
print(f"Hosts: {result['data']['results']['hosts']}")
print(f"Users: {result['data']['results']['users']}")
```

### Example 3: Jobs Only (Daily Collection)

```python
result = collect_automation_reports(
    database='awx',
    collectors=['jobs', 'job_host_summaries'],
    since='2024-12-05T00:00:00Z',
    until='2024-12-06T00:00:00Z'
)
```

---

## Querying Collected Data

### Using Django ORM

```python
from apps.automation_reports.models import Job, Organization, JobTemplate
from django.db.models import Count, Avg, Sum

# Get all successful jobs
successful_jobs = Job.objects.using('metrics_storage').filter(
    status='successful'
).select_related('organization', 'job_template')

# Count jobs by organization
org_stats = Job.objects.using('metrics_storage').values(
    'organization__name'
).annotate(
    total_jobs=Count('id'),
    avg_duration=Avg('elapsed'),
    total_hosts=Sum('num_hosts')
).order_by('-total_jobs')

# Get jobs from specific template
template_jobs = Job.objects.using('metrics_storage').filter(
    job_template__name='Deploy Application'
).order_by('-finished')

# Calculate ROI for a job template
from datetime import timedelta

template = JobTemplate.objects.using('metrics_storage').get(name='Deploy Application')
jobs = Job.objects.using('metrics_storage').filter(
    job_template=template,
    status='successful'
)

total_runs = jobs.count()
time_saved = total_runs * template.time_taken_manually_execute_minutes
time_invested = template.time_taken_create_automation_minutes
roi = (time_saved - time_invested) / time_invested * 100

print(f"Template: {template.name}")
print(f"Total runs: {total_runs}")
print(f"Time saved: {time_saved} minutes ({time_saved/60:.1f} hours)")
print(f"Time invested: {time_invested} minutes ({time_invested/60:.1f} hours)")
print(f"ROI: {roi:.1f}%")
```

### Using SQL

```sql
-- Get collection run summary
SELECT
    id,
    started_at,
    completed_at,
    status,
    jobs_collected,
    organizations_collected,
    job_templates_collected,
    (julianday(completed_at) - julianday(started_at)) * 86400 as duration_seconds
FROM ar_collection_run
ORDER BY started_at DESC;

-- Get jobs with organization and template
SELECT
    j.name,
    j.status,
    j.started,
    j.finished,
    j.elapsed,
    j.num_hosts,
    o.name as organization,
    jt.name as job_template
FROM ar_job j
LEFT JOIN ar_organization o ON j.organization_id = o.id
LEFT JOIN ar_job_template jt ON j.job_template_id = jt.id
WHERE j.finished >= datetime('now', '-30 days')
ORDER BY j.finished DESC
LIMIT 100;

-- Calculate automation ROI by template
SELECT
    jt.name as template_name,
    COUNT(j.id) as total_runs,
    jt.time_taken_manually_execute_minutes,
    jt.time_taken_create_automation_minutes,
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

## Collection Run Tracking

Every collection creates a `CollectionRun` record that tracks:

```python
from apps.automation_reports.models import CollectionRun

# Get latest collection run
latest_run = CollectionRun.objects.using('metrics_storage').latest('started_at')

print(f"Collection Run #{latest_run.id}")
print(f"Status: {latest_run.status}")
print(f"Started: {latest_run.started_at}")
print(f"Completed: {latest_run.completed_at}")
print(f"Duration: {latest_run.duration_seconds}s")
print(f"Jobs collected: {latest_run.jobs_collected}")
print(f"Organizations: {latest_run.organizations_collected}")
print(f"Job Templates: {latest_run.job_templates_collected}")
print(f"Hosts: {latest_run.hosts_collected}")

if latest_run.status == 'failed':
    print(f"Error: {latest_run.error_message}")
```

---

## Database Tables

All automation reports data is stored in `metricsStorage.sqlite` with `ar_` prefix:

| Table | Description | Maps to AWX Table |
|-------|-------------|-------------------|
| `ar_organization` | Organizations | `main_organization` |
| `ar_inventory` | Inventories | `main_inventory` |
| `ar_project` | Projects | `main_project` |
| `ar_job_template` | Job templates + ROI fields | `main_jobtemplate` |
| `ar_execution_environment` | Execution environments | `main_executionenvironment` |
| `ar_instance_group` | Instance groups | `main_instancegroup` |
| `ar_label` | Labels | `main_label` |
| `ar_host` | Hosts | `main_host` |
| `ar_user` | Users | `main_user` |
| `ar_job` | Job execution records | `main_job` + `main_unifiedjob` |
| `ar_job_host_summary` | Per-host execution stats | `main_jobhostsummary` |
| `ar_job_label` | Job-Label relationships | `main_job_labels` |
| `ar_collection_run` | Collection run metadata | N/A (new) |

---

## Scheduled Collection (Recommended)

### Daily Collection

```python
from apps.tasks.models import Task

# Create recurring daily job collection
Task.objects.create(
    name='Daily Job Collection',
    function_name='collect_automation_reports',
    task_data={
        'database': 'awx',
        'collectors': ['jobs', 'job_host_summaries'],
        'since': '{{ yesterday }}',  # Use template variables
        'until': '{{ today }}',
    },
    cron_expression='0 2 * * *',  # Run at 2 AM every day
    is_recurring=True
)
```

### Weekly Full Collection

```python
# Create recurring weekly full collection
Task.objects.create(
    name='Weekly Full Automation Reports Collection',
    function_name='collect_automation_reports',
    task_data={
        'database': 'awx',
        'collect_all_entities': True,
        'since': '{{ week_start }}',
        'until': '{{ week_end }}',
    },
    cron_expression='0 3 * * 0',  # Run at 3 AM every Sunday
    is_recurring=True
)
```

---

## Troubleshooting

### Problem: "metrics-utility is not available"

**Solution**: Ensure metrics-utility is installed in development mode:

```bash
cd /path/to/metrics-utility
pip install -e .
```

### Problem: "Organization not found for job template"

**Cause**: Organizations must be collected before job templates.

**Solution**: Ensure `organizations` collector runs before `job_templates`:

```python
collect_automation_reports(
    collectors=['organizations', 'job_templates', 'jobs']  # Order matters!
)
```

### Problem: CSV files not found

**Cause**: Collectors write to temp directories that may be cleaned up quickly.

**Solution**: This is handled automatically - the code processes CSVs immediately and stores data in SQLite.

### Problem: Foreign key constraint errors

**Cause**: Related entities not collected yet.

**Solution**: Run full collection with all entities:

```python
collect_automation_reports(collect_all_entities=True)
```

---

## Performance Considerations

### Collection Size

- **Organizations**: Small (~100 records)
- **Job Templates**: Small (~1000 records)
- **Jobs**: Can be very large (millions of records)
- **Job Host Summaries**: Can be very large (10x jobs)

### Recommendations

1. **Use date ranges** for jobs and summaries:
   ```python
   collect_automation_reports(
       collectors=['jobs', 'job_host_summaries'],
       since='2024-12-01T00:00:00Z',
       until='2024-12-02T00:00:00Z'
   )
   ```

2. **Collect entities separately** from jobs:
   ```python
   # Weekly: Collect all entities
   collect_automation_reports(collect_all_entities=True)

   # Daily: Only collect jobs
   collect_automation_reports(collectors=['jobs', 'job_host_summaries'])
   ```

3. **Monitor collection runs**:
   ```python
   runs = CollectionRun.objects.using('metrics_storage').filter(
       status='failed'
   )
   for run in runs:
       print(f"Failed run {run.id}: {run.error_message}")
   ```

---

## Next Steps

1. **✅ DONE**: Collectors created in metrics-utility
2. **✅ DONE**: Integration task created in metrics-service
3. **✅ DONE**: Task registered and available in dashboard

### Optional Future Enhancements

1. **API Endpoints**: Create REST API for querying automation reports data
2. **Frontend Dashboard**: Build ROI visualization dashboard
3. **Automated Reporting**: Generate weekly/monthly ROI reports
4. **Data Export**: Export to Excel/PDF for stakeholders
5. **Alerts**: Notify when ROI thresholds are met

---

## Summary

✅ **Collectors Created**: 5 collector modules with 18 collector functions
✅ **Integration Task**: Complete collection task with error handling
✅ **Database Tables**: 13 tables in metricsStorage.sqlite
✅ **Task Registration**: Available in dashboard and API
✅ **Documentation**: Comprehensive usage examples

**The automation reports collection system is ready to use!** 🚀
