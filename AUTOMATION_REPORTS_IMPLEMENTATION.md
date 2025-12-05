# Automation Reports Implementation

## Summary

✅ **Successfully created a new Django app** to store AWX/Controller job data in the shared SQLite database.

Based on the [ansible/automation-reports](https://github.com/ansible/automation-reports) models, simplified for direct SQL collection.

---

## What Was Created

### 1. Django App: `apps/automation_reports/`

**Purpose**: Store AWX/Controller job execution data collected directly from the source PostgreSQL database.

**Database**: `metricsStorage.sqlite` (shared with metrics_storage app, tables prefixed with `ar_`)

**Key Differences from Original**:
- ❌ No Cluster model (single source assumed)
- ❌ No API sync logic (you'll collect via direct SQL)
- ❌ No scheduling models (handled by tasks)
- ✅ Simplified for direct database-to-database collection
- ✅ Optimized for SQLite storage
- ✅ Focused on reporting data only

### 2. Database Models Created

#### Core Entity Models (11 models)

| Model | Table | Purpose | Maps to AWX Table |
|-------|-------|---------|-------------------|
| `Organization` | `ar_organization` | Organizations | `main_organization` |
| `Inventory` | `ar_inventory` | Inventories | `main_inventory` |
| `Project` | `ar_project` | Projects/SCM | `main_project` |
| `JobTemplate` | `ar_job_template` | Job templates with ROI fields | `main_jobtemplate` |
| `ExecutionEnvironment` | `ar_execution_environment` | EE containers | `main_executionenvironment` |
| `InstanceGroup` | `ar_instance_group` | Instance groups | `main_instancegroup` |
| `Label` | `ar_label` | Job labels | `main_label` |
| `Host` | `ar_host` | Managed hosts | `main_host` |
| `AAPUser` | `ar_user` | Users who launched jobs | `main_user` |

#### Job Data Models (3 models)

| Model | Table | Purpose | Maps to AWX Table |
|-------|-------|---------|-------------------|
| `Job` | `ar_job` | Job execution records | `main_job` + `main_unifiedjob` |
| `JobHostSummary` | `ar_job_host_summary` | Per-host execution stats | `main_jobhostsummary` |
| `JobLabel` | `ar_job_label` | Job-Label relationships | `main_job_labels` |

#### Collection Metadata (1 model)

| Model | Table | Purpose |
|-------|-------|---------|
| `CollectionRun` | `ar_collection_run` | Tracks each collection run |

### 3. Database Tables Created

```bash
# Verify tables exist
sqlite3 metricsStorage.sqlite ".tables"

# Output (automation reports tables prefixed with ar_):
ar_collection_run         ar_job                    ar_organization
ar_execution_environment  ar_job_host_summary       ar_project
ar_host                   ar_job_label              ar_user
ar_instance_group         ar_job_template           collection_runs
ar_inventory              ar_label                  metric_data
```

### 4. Configuration Changes

#### `metrics_service/settings/defaults.py`

```python
# Added to LOCAL_APPS
LOCAL_APPS = [
    ...
    "apps.automation_reports",  # Automation reports data (AWX/Controller jobs)
]

# Using shared SQLite database (no changes needed)
DATABASES = {
    ...
    "metrics_storage": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "metricsStorage.sqlite",  # Shared database
    },
}

# Added database router
DATABASE_ROUTERS = [
    "apps.metrics_storage.database_router.MetricsStorageRouter",
    "apps.automation_reports.database_router.AutomationReportsRouter",  # Routes to metrics_storage
]
```

---

## Model Field Details

### Job Model (Main Model)

The `Job` model captures comprehensive job execution data:

```python
class Job(BaseTimestampModel):
    external_id = IntegerField()  # AWX job ID

    # Job identification
    name = CharField()
    description = TextField()
    type = CharField(choices=JobTypeChoices)  # job, playbook_run
    job_type = CharField(choices=JobRunTypeChoices)  # run, check, scan
    launch_type = CharField(choices=JobLaunchTypeChoices)  # manual, scheduled, etc.
    status = CharField(choices=JobStatusChoices)  # successful, failed, etc.

    # Relationships
    organization = ForeignKey(Organization)
    job_template = ForeignKey(JobTemplate)
    inventory = ForeignKey(Inventory)
    project = ForeignKey(Project)
    execution_environment = ForeignKey(ExecutionEnvironment)
    instance_group = ForeignKey(InstanceGroup)
    launched_by = ForeignKey(AAPUser)

    # Timing
    started = DateTimeField()
    finished = DateTimeField()
    elapsed = DecimalField()  # Duration in seconds

    # Host counts (critical for reporting!)
    num_hosts = IntegerField()
    changed_hosts_count = IntegerField()
    dark_hosts_count = IntegerField()
    failures_hosts_count = IntegerField()
    ok_hosts_count = IntegerField()
    processed_hosts_count = IntegerField()
    skipped_hosts_count = IntegerField()
    failed_hosts_count = IntegerField()
    ignored_hosts_count = IntegerField()
    rescued_hosts_count = IntegerField()
```

### JobTemplate Model (with ROI Fields)

```python
class JobTemplate(BaseTimestampModel):
    external_id = IntegerField()
    name = CharField()
    organization = ForeignKey(Organization)

    # ROI calculation fields
    time_taken_manually_execute_minutes = BigIntegerField(default=60)
    time_taken_create_automation_minutes = BigIntegerField(default=240)
```

---

## Next Steps: Implementing Collection

### Option 1: Direct SQL Collection (Recommended)

Create a task that queries AWX PostgreSQL directly and inserts into SQLite:

```python
# apps/tasks/tasks_automation_reports.py

from django.db import connections
from apps.automation_reports.models import (
    Organization, JobTemplate, Job, JobHostSummary,
    CollectionRun
)


@task(queue="automation_reports", decorate=False)
def collect_awx_job_data(**kwargs):
    """
    Collect job data directly from AWX PostgreSQL database.

    Args:
        date_from (str): Start date (ISO format)
        date_to (str): End date (ISO format)
        source_database (str): Database name (default: 'awx')
    """
    from django.db import transaction

    date_from = kwargs.get('date_from')
    date_to = kwargs.get('date_to')
    source_db = kwargs.get('source_database', 'awx')

    # Create collection run
    collection_run = CollectionRun.objects.using('metrics_storage').create(
        source_database=source_db,
        date_from=date_from,
        date_to=date_to,
        status='running'
    )

    try:
        # Get source database connection
        source_conn = connections[source_db]

        with transaction.atomic(using='metrics_storage'):
            # 1. Collect Organizations
            orgs_collected = _collect_organizations(source_conn)

            # 2. Collect Job Templates
            templates_collected = _collect_job_templates(source_conn)

            # 3. Collect Jobs (main data)
            jobs_collected = _collect_jobs(source_conn, date_from, date_to)

            # 4. Collect Job Host Summaries
            hosts_collected = _collect_job_host_summaries(source_conn, date_from, date_to)

        # Mark collection as completed
        collection_run.mark_completed(
            jobs_collected=jobs_collected,
            organizations_collected=orgs_collected,
            job_templates_collected=templates_collected,
            hosts_collected=hosts_collected
        )

        return {
            'status': 'success',
            'collection_run_id': collection_run.id,
            'jobs_collected': jobs_collected,
            'organizations_collected': orgs_collected
        }

    except Exception as e:
        collection_run.mark_failed(str(e))
        return {'status': 'error', 'error': str(e)}


def _collect_organizations(source_conn):
    """Collect organizations from AWX database."""
    with source_conn.cursor() as cursor:
        cursor.execute("""
            SELECT id, name, description
            FROM main_organization
            WHERE NOT is_template
        """)

        count = 0
        for row in cursor.fetchall():
            Organization.objects.using('metrics_storage').update_or_create(
                external_id=row[0],
                defaults={
                    'name': row[1],
                    'description': row[2]
                }
            )
            count += 1

        return count


def _collect_job_templates(source_conn):
    """Collect job templates from AWX database."""
    with source_conn.cursor() as cursor:
        cursor.execute("""
            SELECT
                jt.id,
                jt.name,
                jt.description,
                jt.organization_id
            FROM main_jobtemplate jt
            WHERE jt.is_template = false
        """)

        count = 0
        for row in cursor.fetchall():
            org = None
            if row[3]:
                try:
                    org = Organization.objects.using('metrics_storage').get(
                        external_id=row[3]
                    )
                except Organization.DoesNotExist:
                    pass

            JobTemplate.objects.using('metrics_storage').update_or_create(
                external_id=row[0],
                defaults={
                    'name': row[1],
                    'description': row[2],
                    'organization': org
                }
            )
            count += 1

        return count


def _collect_jobs(source_conn, date_from, date_to):
    """Collect jobs from AWX database."""
    with source_conn.cursor() as cursor:
        sql = """
            SELECT
                j.id,
                j.name,
                j.description,
                j.job_type,
                j.launch_type,
                j.status,
                j.started,
                j.finished,
                j.elapsed,
                j.failed,
                j.job_template_id,
                j.inventory_id,
                j.project_id,
                j.organization_id,
                j.execution_environment_id,
                j.instance_group_id,
                j.created_by_id,
                u.created,
                u.modified,
                -- Host counts
                COALESCE(
                    (SELECT COUNT(DISTINCT host_id)
                     FROM main_jobhostsummary
                     WHERE job_id = j.id), 0
                ) as num_hosts,
                -- Add other host count aggregations as needed
                0 as changed_hosts_count,
                0 as dark_hosts_count,
                0 as failures_hosts_count,
                0 as ok_hosts_count,
                0 as processed_hosts_count,
                0 as skipped_hosts_count,
                0 as failed_hosts_count,
                0 as ignored_hosts_count,
                0 as rescued_hosts_count
            FROM main_job j
            JOIN main_unifiedjob u ON j.unifiedjob_ptr_id = u.id
            WHERE 1=1
        """

        params = []
        if date_from:
            sql += " AND j.finished >= %s"
            params.append(date_from)
        if date_to:
            sql += " AND j.finished <= %s"
            params.append(date_to)

        sql += " ORDER BY j.finished DESC"

        cursor.execute(sql, params)

        count = 0
        for row in cursor.fetchall():
            # Get related objects
            job_template = _get_or_none(JobTemplate, row[10])
            organization = _get_or_none(Organization, row[13])

            Job.objects.using('metrics_storage').update_or_create(
                external_id=row[0],
                defaults={
                    'name': row[1],
                    'description': row[2],
                    'job_type': row[3],
                    'launch_type': row[4],
                    'status': row[5],
                    'started': row[6],
                    'finished': row[7],
                    'elapsed': row[8],
                    'failed': row[9],
                    'job_template': job_template,
                    'organization': organization,
                    'created': row[17],
                    'modified': row[18],
                    'num_hosts': row[19],
                    # ... other fields
                }
            )
            count += 1

        return count


def _get_or_none(model_class, external_id):
    """Helper to get related object or None."""
    if external_id is None:
        return None
    try:
        return model_class.objects.using('metrics_storage').get(
            external_id=external_id
        )
    except model_class.DoesNotExist:
        return None
```

### Option 2: Using Django ORM (Alternative)

Query AWX using Django ORM and copy to automation reports:

```python
from django.db import connections

# Query AWX database
with connections['awx'].cursor() as cursor:
    cursor.execute("SELECT * FROM main_job WHERE ...")
    # Process results
```

---

## Usage Examples

### 1. Manual Collection

```python
# Django shell
python manage.py shell

from apps.automation_reports.models import *
from django.utils import timezone
from datetime import timedelta

# Create an organization
org = Organization.objects.using('metrics_storage').create(
    external_id=1,
    name="Default",
    description="Default organization"
)

# Create a job template
template = JobTemplate.objects.using('metrics_storage').create(
    external_id=7,
    name="Deploy Application",
    organization=org,
    time_taken_manually_execute_minutes=120,
    time_taken_create_automation_minutes=480
)

# Create a job
job = Job.objects.using('metrics_storage').create(
    external_id=123,
    name="Deploy Application",
    job_template=template,
    organization=org,
    status="successful",
    started=timezone.now() - timedelta(hours=1),
    finished=timezone.now(),
    elapsed=3600,  # 1 hour
    num_hosts=10,
    ok_hosts_count=10
)
```

### 2. Query Jobs

```python
# Get all successful jobs
successful_jobs = Job.objects.using('metrics_storage').filter(
    status='successful'
).select_related('job_template', 'organization')

# Get jobs from last 30 days
from datetime import timedelta
from django.utils import timezone

thirty_days_ago = timezone.now() - timedelta(days=30)
recent_jobs = Job.objects.using('metrics_storage').filter(
    finished__gte=thirty_days_ago
).order_by('-finished')

# Aggregate by organization
from django.db.models import Count, Avg

org_stats = Job.objects.using('metrics_storage').values(
    'organization__name'
).annotate(
    total_jobs=Count('id'),
    avg_duration=Avg('elapsed')
)
```

### 3. Track Collections

```python
# View collection runs
collections = CollectionRun.objects.using('metrics_storage').all()

for collection in collections:
    print(f"Collection {collection.id}: {collection.status}")
    print(f"  Jobs collected: {collection.jobs_collected}")
    print(f"  Duration: {collection.duration_seconds}s")
```

---

## Database Schema Overview

### Entity Relationship

```
Organization
├── JobTemplate (many)
├── Inventory (many)
├── Project (many)
├── Label (many)
└── Job (many)
    ├── JobLabel (many-to-many through)
    └── JobHostSummary (many)
        └── Host

AAPUser
└── Job (many, as launched_by)

ExecutionEnvironment
└── Job (many)

InstanceGroup
└── Job (many)
```

### Key Indexes Created

```python
# Job model indexes
- status + finished (for filtering by status and time)
- job_template + finished (for template-based reporting)
- organization + finished (for org-based reporting)
- started (for time-based queries)

# JobHostSummary indexes
- job + host_name (for per-job host lookups)
- host + created (for host-based reporting)
```

---

## Integration with Metrics Service

### Task Registration

Add to `apps/tasks/tasks.py`:

```python
from apps.tasks.tasks_automation_reports import collect_awx_job_data

TASK_FUNCTIONS = {
    ...
    "collect_awx_job_data": collect_awx_job_data,
}

TASK_METADATA = {
    ...
    "collect_awx_job_data": {
        "category": "Automation Reports",
        "description": "Collect job data from AWX/Controller database",
        "input_schema": {...},
    }
}
```

### API Endpoints (Future)

Create endpoints similar to metrics_storage:

```
/api/v1/automation-reports/jobs/
/api/v1/automation-reports/organizations/
/api/v1/automation-reports/job-templates/
/api/v1/automation-reports/stats/
```

---

## Files Created/Modified

### New Files

```
apps/automation_reports/
├── __init__.py
├── apps.py                      # App configuration
├── models.py                    # 14 models (11 entities + 3 job models)
├── database_router.py           # SQLite routing
├── migrations/
│   └── 0001_initial.py         # Initial migration
└── (other Django app files)

AUTOMATION_REPORTS_IMPLEMENTATION.md  # This file
```

**Note**: Tables are stored in the shared `metricsStorage.sqlite` database with `ar_` prefix.

### Modified Files

```
metrics_service/settings/defaults.py
├── Added apps.automation_reports to LOCAL_APPS
└── Added AutomationReportsRouter to DATABASE_ROUTERS
    (routes to existing metrics_storage database)

apps/automation_reports/database_router.py
└── Routes queries to 'metrics_storage' database
```

---

## Next Steps

1. **✅ DONE**: Models created, migrations run, database initialized

2. **TODO**: Create SQL collection task
   - [ ] Create `apps/tasks/tasks_automation_reports.py`
   - [ ] Implement SQL queries to collect from AWX PostgreSQL
   - [ ] Register task in `apps/tasks/tasks.py`
   - [ ] Test collection with real AWX database

3. **TODO**: Create API endpoints
   - [ ] Create `apps/api/v1/automation_reports/` directory
   - [ ] Create serializers for models
   - [ ] Create viewsets with filtering/pagination
   - [ ] Register URLs

4. **TODO**: Create frontend dashboard
   - [ ] Design job execution timeline
   - [ ] Create organization/template drill-down views
   - [ ] Add ROI calculations display
   - [ ] Integrate with existing dashboard

5. **TODO**: Testing
   - [ ] Unit tests for models
   - [ ] Integration tests for collection task
   - [ ] API endpoint tests

---

## SQL Query Examples for AWX Database

### Get Jobs with Full Details

```sql
SELECT
    j.id,
    j.name,
    j.status,
    j.started,
    j.finished,
    j.elapsed,
    j.job_type,
    j.launch_type,
    jt.name as job_template_name,
    org.name as organization_name,
    inv.name as inventory_name,
    prj.name as project_name,
    ee.name as execution_environment,
    ig.name as instance_group,
    u.username as launched_by,
    -- Host counts
    (SELECT COUNT(DISTINCT host_id) FROM main_jobhostsummary WHERE job_id = j.id) as num_hosts,
    (SELECT SUM(changed) FROM main_jobhostsummary WHERE job_id = j.id) as changed_hosts,
    (SELECT SUM(ok) FROM main_jobhostsummary WHERE job_id = j.id) as ok_hosts,
    (SELECT SUM(failures) FROM main_jobhostsummary WHERE job_id = j.id) as failed_hosts
FROM main_job j
LEFT JOIN main_jobtemplate jt ON j.job_template_id = jt.id
LEFT JOIN main_organization org ON j.organization_id = org.id
LEFT JOIN main_inventory inv ON j.inventory_id = inv.id
LEFT JOIN main_project prj ON j.project_id = prj.id
LEFT JOIN main_executionenvironment ee ON j.execution_environment_id = ee.id
LEFT JOIN main_instancegroup ig ON j.instance_group_id = ig.id
LEFT JOIN main_user u ON j.created_by_id = u.id
WHERE j.finished BETWEEN '2024-01-01' AND '2024-12-31'
  AND j.status IN ('successful', 'failed')
ORDER BY j.finished DESC
LIMIT 1000;
```

### Get Job Host Summaries

```sql
SELECT
    jhs.id,
    jhs.job_id,
    h.name as host_name,
    jhs.changed,
    jhs.dark,
    jhs.failures,
    jhs.ok,
    jhs.processed,
    jhs.skipped,
    jhs.failed,
    jhs.ignored,
    jhs.rescued,
    jhs.created,
    jhs.modified
FROM main_jobhostsummary jhs
LEFT JOIN main_host h ON jhs.host_id = h.id
WHERE jhs.job_id IN (
    SELECT id FROM main_job
    WHERE finished BETWEEN '2024-01-01' AND '2024-12-31'
);
```

---

## Summary

✅ **Complete Django app created** with 14 models to store AWX/Controller job data
✅ **Shared SQLite database** - tables stored in `metricsStorage.sqlite` with `ar_` prefix
✅ **Database routing configured** - all automation_reports queries go to metrics_storage database
✅ **Migrations created and applied** - database ready to use (13 tables created)
✅ **Optimized for direct SQL collection** from AWX PostgreSQL database

**Next**: Implement the SQL collection task to populate the database! 🚀
