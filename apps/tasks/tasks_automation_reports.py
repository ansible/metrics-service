"""
Automation Reports collection tasks for metrics_service.

This module provides tasks for collecting AWX/Controller job data using
metrics-utility collectors and storing it in the automation_reports tables.
"""

import csv
import logging
import os
from datetime import UTC, datetime
from typing import Any

from django.db import connections, transaction

from apps.automation_reports.models import (
    AAPUser,
    CollectionRun,
    ExecutionEnvironment,
    Host,
    InstanceGroup,
    Inventory,
    Job,
    JobHostSummary,
    JobTemplate,
    Label,
    Organization,
    Project,
)

from .utils import create_task_result, log_task_execution, task_execution_wrapper

logger = logging.getLogger(__name__)

# Import metrics-utility collectors
try:
    from metrics_utility.library.collectors.controller import (
        automation_reports_execution_environments,
        automation_reports_hosts,
        automation_reports_instance_groups,
        automation_reports_inventories,
        automation_reports_job_host_summaries,
        automation_reports_job_templates,
        automation_reports_jobs,
        automation_reports_labels,
        automation_reports_organizations,
        automation_reports_projects,
        automation_reports_users,
    )

    METRICS_UTILITY_AVAILABLE = True
except ImportError as e:
    logger.warning(f"metrics-utility automation reports collectors not available: {e}")
    METRICS_UTILITY_AVAILABLE = False

try:
    from dispatcherd.publish import task
except ImportError:

    def task():
        def decorator(func):
            return func

        return decorator


def _read_csv_file(csv_path):
    """
    Read a CSV file and return rows as list of dictionaries.

    Args:
        csv_path: Path to CSV file

    Returns:
        List of dictionaries, one per row
    """
    if not os.path.exists(csv_path):
        logger.warning(f"CSV file not found: {csv_path}")
        return []

    rows = []
    try:
        with open(csv_path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows.append(row)
    except Exception as e:
        logger.error(f"Error reading CSV file {csv_path}: {e}")
        return []

    return rows


def _process_organizations(csv_files, collection_run):
    """
    Process organizations from CSV files and store in database.

    Args:
        csv_files: List of CSV file paths
        collection_run: CollectionRun instance

    Returns:
        Number of organizations created/updated
    """
    count = 0
    for csv_path in csv_files:
        rows = _read_csv_file(csv_path)
        for row in rows:
            Organization.objects.using("metrics_storage").update_or_create(
                external_id=int(row["external_id"]),
                defaults={
                    "name": row["name"],
                    "description": row.get("description") or "",
                },
            )
            count += 1

    logger.info(f"Processed {count} organizations")
    return count


def _process_job_templates(csv_files, collection_run):
    """
    Process job templates from CSV files and store in database.

    Args:
        csv_files: List of CSV file paths
        collection_run: CollectionRun instance

    Returns:
        Number of job templates created/updated
    """
    count = 0
    for csv_path in csv_files:
        rows = _read_csv_file(csv_path)
        for row in rows:
            # Get related organization
            organization = None
            if row.get("organization_id"):
                try:
                    organization = Organization.objects.using("metrics_storage").get(
                        external_id=int(row["organization_id"])
                    )
                except Organization.DoesNotExist:
                    logger.warning(
                        f"Organization {row['organization_id']} not found for job template {row['external_id']}"
                    )

            JobTemplate.objects.using("metrics_storage").update_or_create(
                external_id=int(row["external_id"]),
                defaults={
                    "name": row["name"],
                    "description": row.get("description") or "",
                    "organization": organization,
                    "time_taken_manually_execute_minutes": int(row.get("time_taken_manually_execute_minutes", 60)),
                    "time_taken_create_automation_minutes": int(row.get("time_taken_create_automation_minutes", 240)),
                },
            )
            count += 1

    logger.info(f"Processed {count} job templates")
    return count


def _process_jobs(csv_files, collection_run):
    """
    Process jobs from CSV files and store in database.

    Args:
        csv_files: List of CSV file paths
        collection_run: CollectionRun instance

    Returns:
        Number of jobs created/updated
    """
    count = 0
    for csv_path in csv_files:
        rows = _read_csv_file(csv_path)
        for row in rows:
            # Get related objects
            organization = _get_by_external_id(Organization, row.get("organization_id"))
            job_template = _get_by_external_id(JobTemplate, row.get("job_template_id"))
            inventory = _get_by_external_id(Inventory, row.get("inventory_id"))
            project = _get_by_external_id(Project, row.get("project_id"))
            execution_environment = _get_by_external_id(ExecutionEnvironment, row.get("execution_environment_id"))
            instance_group = _get_by_external_id(InstanceGroup, row.get("instance_group_id"))
            launched_by = _get_by_external_id(AAPUser, row.get("created_by_id"))

            Job.objects.using("metrics_storage").update_or_create(
                external_id=int(row["external_id"]),
                defaults={
                    "name": row["name"],
                    "description": row.get("description") or "",
                    "type": row.get("type", "job"),
                    "job_type": row.get("job_type", "run"),
                    "launch_type": row.get("launch_type", "manual"),
                    "status": row["status"],
                    "started": row.get("started"),
                    "finished": row.get("finished"),
                    "elapsed": float(row.get("elapsed", 0)),
                    "failed": row.get("failed", "false").lower() == "true",
                    "created": row.get("created"),
                    "modified": row.get("modified"),
                    "organization": organization,
                    "job_template": job_template,
                    "inventory": inventory,
                    "project": project,
                    "execution_environment": execution_environment,
                    "instance_group": instance_group,
                    "launched_by": launched_by,
                    # Host counts
                    "num_hosts": int(row.get("num_hosts", 0)),
                    "changed_hosts_count": int(row.get("changed_hosts_count", 0)),
                    "dark_hosts_count": int(row.get("dark_hosts_count", 0)),
                    "failures_hosts_count": int(row.get("failures_hosts_count", 0)),
                    "ok_hosts_count": int(row.get("ok_hosts_count", 0)),
                    "processed_hosts_count": int(row.get("processed_hosts_count", 0)),
                    "skipped_hosts_count": int(row.get("skipped_hosts_count", 0)),
                    "failed_hosts_count": int(row.get("failed_hosts_count", 0)),
                    "ignored_hosts_count": int(row.get("ignored_hosts_count", 0)),
                    "rescued_hosts_count": int(row.get("rescued_hosts_count", 0)),
                },
            )
            count += 1

    logger.info(f"Processed {count} jobs")
    return count


def _process_job_host_summaries(csv_files, collection_run):
    """
    Process job host summaries from CSV files and store in database.

    Args:
        csv_files: List of CSV file paths
        collection_run: CollectionRun instance

    Returns:
        Number of job host summaries created/updated
    """
    count = 0
    for csv_path in csv_files:
        rows = _read_csv_file(csv_path)
        for row in rows:
            # Get related objects
            job = _get_by_external_id(Job, row.get("job_id"))
            host = _get_by_external_id(Host, row.get("host_id"))

            if not job:
                logger.warning(f"Job {row.get('job_id')} not found for job host summary")
                continue

            JobHostSummary.objects.using("metrics_storage").update_or_create(
                job=job,
                host_name=row.get("host_name", ""),
                defaults={
                    "host": host,
                    "changed": int(row.get("changed", 0)),
                    "dark": int(row.get("dark", 0)),
                    "failures": int(row.get("failures", 0)),
                    "ok": int(row.get("ok", 0)),
                    "processed": int(row.get("processed", 0)),
                    "skipped": int(row.get("skipped", 0)),
                    "failed": row.get("failed", "false").lower() == "true",
                    "ignored": int(row.get("ignored", 0)),
                    "rescued": int(row.get("rescued", 0)),
                    "created": row.get("created"),
                    "modified": row.get("modified"),
                },
            )
            count += 1

    logger.info(f"Processed {count} job host summaries")
    return count


def _process_supporting_entities(csv_files_dict, collection_run):  # noqa: C901, PLR0912, PLR0915
    """
    Process supporting entities (inventories, projects, hosts, users, etc.).

    Args:
        csv_files_dict: Dictionary mapping entity type to CSV file paths
        collection_run: CollectionRun instance

    Returns:
        Dictionary with counts for each entity type
    """
    counts = {}

    # Process inventories
    if "inventories" in csv_files_dict:
        count = 0
        for csv_path in csv_files_dict["inventories"]:
            rows = _read_csv_file(csv_path)
            for row in rows:
                organization = _get_by_external_id(Organization, row.get("organization_id"))
                Inventory.objects.using("metrics_storage").update_or_create(
                    external_id=int(row["external_id"]),
                    defaults={
                        "name": row["name"],
                        "description": row.get("description") or "",
                        "organization": organization,
                    },
                )
                count += 1
        counts["inventories"] = count
        logger.info(f"Processed {count} inventories")

    # Process projects
    if "projects" in csv_files_dict:
        count = 0
        for csv_path in csv_files_dict["projects"]:
            rows = _read_csv_file(csv_path)
            for row in rows:
                organization = _get_by_external_id(Organization, row.get("organization_id"))
                Project.objects.using("metrics_storage").update_or_create(
                    external_id=int(row["external_id"]),
                    defaults={
                        "name": row["name"],
                        "description": row.get("description") or "",
                        "scm_type": row.get("scm_type") or "",
                        "organization": organization,
                    },
                )
                count += 1
        counts["projects"] = count
        logger.info(f"Processed {count} projects")

    # Process hosts
    if "hosts" in csv_files_dict:
        count = 0
        for csv_path in csv_files_dict["hosts"]:
            rows = _read_csv_file(csv_path)
            for row in rows:
                inventory = _get_by_external_id(Inventory, row.get("inventory_id"))
                Host.objects.using("metrics_storage").update_or_create(
                    external_id=int(row["external_id"]),
                    defaults={
                        "name": row["name"],
                        "description": row.get("description") or "",
                        "inventory": inventory,
                    },
                )
                count += 1
        counts["hosts"] = count
        logger.info(f"Processed {count} hosts")

    # Process users
    if "users" in csv_files_dict:
        count = 0
        for csv_path in csv_files_dict["users"]:
            rows = _read_csv_file(csv_path)
            for row in rows:
                AAPUser.objects.using("metrics_storage").update_or_create(
                    external_id=int(row["external_id"]),
                    defaults={
                        "username": row["username"],
                        "first_name": row.get("first_name") or "",
                        "last_name": row.get("last_name") or "",
                        "email": row.get("email") or "",
                        "user_type": row.get("user_type", "normal"),
                    },
                )
                count += 1
        counts["users"] = count
        logger.info(f"Processed {count} users")

    # Process execution environments
    if "execution_environments" in csv_files_dict:
        count = 0
        for csv_path in csv_files_dict["execution_environments"]:
            rows = _read_csv_file(csv_path)
            for row in rows:
                ExecutionEnvironment.objects.using("metrics_storage").update_or_create(
                    external_id=int(row["external_id"]),
                    defaults={
                        "name": row["name"],
                        "description": row.get("description") or "",
                        "image": row.get("image") or "",
                    },
                )
                count += 1
        counts["execution_environments"] = count
        logger.info(f"Processed {count} execution environments")

    # Process instance groups
    if "instance_groups" in csv_files_dict:
        count = 0
        for csv_path in csv_files_dict["instance_groups"]:
            rows = _read_csv_file(csv_path)
            for row in rows:
                InstanceGroup.objects.using("metrics_storage").update_or_create(
                    external_id=int(row["external_id"]),
                    defaults={
                        "name": row["name"],
                        "is_container_group": row.get("is_container_group", "false").lower() == "true",
                    },
                )
                count += 1
        counts["instance_groups"] = count
        logger.info(f"Processed {count} instance groups")

    # Process labels
    if "labels" in csv_files_dict:
        count = 0
        for csv_path in csv_files_dict["labels"]:
            rows = _read_csv_file(csv_path)
            for row in rows:
                organization = _get_by_external_id(Organization, row.get("organization_id"))
                Label.objects.using("metrics_storage").update_or_create(
                    external_id=int(row["external_id"]),
                    defaults={
                        "name": row["name"],
                        "organization": organization,
                    },
                )
                count += 1
        counts["labels"] = count
        logger.info(f"Processed {count} labels")

    return counts


def _get_by_external_id(model_class, external_id):
    """
    Get a model instance by external_id.

    Args:
        model_class: Model class to query
        external_id: External ID value

    Returns:
        Model instance or None
    """
    if not external_id:
        return None

    try:
        return model_class.objects.using("metrics_storage").get(external_id=int(external_id))
    except (model_class.DoesNotExist, ValueError):
        return None


@task(queue="automation_reports", decorate=False)
@task_execution_wrapper("collect_automation_reports")
def collect_automation_reports(**kwargs) -> dict[str, Any]:  # noqa: PLR0915
    """
    Collect automation reports data from AWX/Controller database.

    This task collects job execution data, organizations, templates, and related
    entities from the AWX/Controller database and stores them in the automation
    reports tables.

    Args:
        **kwargs: Task parameters:
            - database (str): Database name from Django settings (default: 'awx')
            - since (str): Start date for collection (ISO format)
            - until (str): End date for collection (ISO format)
            - collectors (list): List of collectors to run (default: all)
            - collect_all_entities (bool): Whether to collect all supporting entities (default: False)

    Returns:
        dict: Task result with collection statistics
    """
    if not METRICS_UTILITY_AVAILABLE:
        return create_task_result("error", error="metrics-utility is not available")

    log_task_execution("collect_automation_reports", "processing", "Collecting automation reports data")

    # Get parameters
    database = kwargs.get("database", "awx")
    since = kwargs.get("since")
    until = kwargs.get("until")
    collectors_list = kwargs.get("collectors", ["organizations", "job_templates", "jobs", "job_host_summaries"])
    collect_all_entities = kwargs.get("collect_all_entities", False)

    # Parse dates
    date_from = None
    date_to = None
    if since:
        date_from = datetime.fromisoformat(since.replace("Z", "+00:00"))
    if until:
        date_to = datetime.fromisoformat(until.replace("Z", "+00:00"))

    # Create collection run
    collection_run = CollectionRun.objects.using("metrics_storage").create(
        source_database=database, date_from=date_from, date_to=date_to, status="running"
    )

    try:
        # Get database connection
        db = connections[database]

        results = {}

        # Use transaction for atomicity
        with transaction.atomic(using="metrics_storage"):
            # Collect organizations (always first, needed for relationships)
            if "organizations" in collectors_list or collect_all_entities:
                logger.info("Collecting organizations...")
                collector = automation_reports_organizations(db=db)
                csv_files = collector.gather()
                results["organizations"] = _process_organizations(csv_files, collection_run)
            else:
                results["organizations"] = 0

            # Collect job templates
            if "job_templates" in collectors_list or collect_all_entities:
                logger.info("Collecting job templates...")
                collector = automation_reports_job_templates(db=db)
                csv_files = collector.gather()
                results["job_templates"] = _process_job_templates(csv_files, collection_run)
            else:
                results["job_templates"] = 0

            # Collect supporting entities if requested
            if collect_all_entities:
                logger.info("Collecting supporting entities...")
                csv_files_dict = {}

                # Inventories
                collector = automation_reports_inventories(db=db)
                csv_files_dict["inventories"] = collector.gather()

                # Projects
                collector = automation_reports_projects(db=db)
                csv_files_dict["projects"] = collector.gather()

                # Hosts
                collector = automation_reports_hosts(db=db)
                csv_files_dict["hosts"] = collector.gather()

                # Users
                collector = automation_reports_users(db=db)
                csv_files_dict["users"] = collector.gather()

                # Execution environments
                collector = automation_reports_execution_environments(db=db)
                csv_files_dict["execution_environments"] = collector.gather()

                # Instance groups
                collector = automation_reports_instance_groups(db=db)
                csv_files_dict["instance_groups"] = collector.gather()

                # Labels
                collector = automation_reports_labels(db=db)
                csv_files_dict["labels"] = collector.gather()

                entity_counts = _process_supporting_entities(csv_files_dict, collection_run)
                results.update(entity_counts)

            # Collect jobs (main data)
            if "jobs" in collectors_list:
                logger.info("Collecting jobs...")
                collector = automation_reports_jobs(db=db, since=date_from, until=date_to)
                csv_files = collector.gather()
                results["jobs"] = _process_jobs(csv_files, collection_run)
            else:
                results["jobs"] = 0

            # Collect job host summaries
            if "job_host_summaries" in collectors_list:
                logger.info("Collecting job host summaries...")
                collector = automation_reports_job_host_summaries(db=db, since=date_from, until=date_to)
                csv_files = collector.gather()
                results["job_host_summaries"] = _process_job_host_summaries(csv_files, collection_run)
            else:
                results["job_host_summaries"] = 0

        # Mark collection as completed
        collection_run.status = "completed"
        collection_run.completed_at = datetime.now(UTC)
        collection_run.jobs_collected = results.get("jobs", 0)
        collection_run.organizations_collected = results.get("organizations", 0)
        collection_run.job_templates_collected = results.get("job_templates", 0)
        collection_run.hosts_collected = results.get("hosts", 0)
        collection_run.save()

        return create_task_result(
            "success",
            data={
                "collection_run_id": collection_run.id,
                "results": results,
                "duration_seconds": collection_run.duration_seconds,
            },
        )

    except Exception as e:
        logger.exception(f"Error collecting automation reports: {e}")
        collection_run.status = "failed"
        collection_run.completed_at = datetime.now(UTC)
        collection_run.error_message = str(e)
        collection_run.save()

        return create_task_result("error", error=str(e))
