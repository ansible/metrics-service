#!/usr/bin/env python
"""
Simple test script for automation reports collectors.
Tests SQL queries directly against AWX PostgreSQL database.
"""

import psycopg

# AWX Database connection parameters
# Adjust these to match your AWX database configuration
DB_CONFIG = {"dbname": "awx", "user": "awx", "password": "awx", "host": "localhost", "port": 5432}


def test_query(conn, query_name, sql_query):
    """Test a SQL query and return results."""

    try:
        with conn.cursor() as cursor:
            cursor.execute(sql_query)

            # Get column names
            columns = [desc[0] for desc in cursor.description]

            # Get row count
            rows = cursor.fetchall()
            len(rows)

            # Show first 3 rows
            if rows:
                for _i, row in enumerate(rows[:3], 1):
                    for _col, val in zip(columns, row, strict=False):
                        # Truncate long values
                        str(val)[:50] if val else "NULL"

            return True

    except Exception:
        import traceback

        traceback.print_exc()
        return False


def main():
    """Run verification tests."""

    # Connect to AWX database
    try:
        conn = psycopg.connect(**DB_CONFIG)
    except Exception:
        return 1

    # Test queries
    tests = [
        (
            "Organizations",
            """
            SELECT
                org.id AS external_id,
                org.name,
                org.description,
                org.created,
                org.modified
            FROM main_organization org
            ORDER BY org.id ASC
            LIMIT 5
        """,
        ),
        (
            "Job Templates",
            """
            SELECT
                jt.id AS external_id,
                jt.name,
                jt.description,
                jt.organization_id,
                jt.project_id,
                jt.inventory_id,
                jt.execution_environment_id,
                jt.created,
                jt.modified,
                60 AS time_taken_manually_execute_minutes,
                240 AS time_taken_create_automation_minutes
            FROM main_jobtemplate jt
            ORDER BY jt.id ASC
            LIMIT 5
        """,
        ),
        (
            "Jobs",
            """
            SELECT
                j.id AS external_id,
                uj.name,
                uj.description,
                'job' AS type,
                j.job_type,
                j.launch_type,
                uj.status,
                uj.started,
                uj.finished,
                uj.elapsed,
                uj.failed,
                uj.created,
                uj.modified,
                j.job_template_id,
                j.inventory_id,
                j.project_id,
                j.organization_id,
                j.execution_environment_id,
                j.instance_group_id,
                uj.created_by_id,
                COALESCE(
                    (SELECT COUNT(DISTINCT host_id)
                     FROM main_jobhostsummary
                     WHERE job_id = j.id), 0
                ) AS num_hosts
            FROM main_job j
            JOIN main_unifiedjob uj ON j.unifiedjob_ptr_id = uj.id
            WHERE uj.finished IS NOT NULL
            ORDER BY uj.finished DESC
            LIMIT 5
        """,
        ),
        (
            "Job Host Summaries",
            """
            SELECT
                jhs.id AS external_id,
                jhs.job_id,
                jhs.host_id,
                jhs.host_name,
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
            ORDER BY jhs.id DESC
            LIMIT 5
        """,
        ),
        (
            "Inventories",
            """
            SELECT
                inv.id AS external_id,
                inv.name,
                inv.description,
                inv.organization_id,
                inv.created,
                inv.modified
            FROM main_inventory inv
            ORDER BY inv.id ASC
            LIMIT 5
        """,
        ),
        (
            "Projects",
            """
            SELECT
                proj.id AS external_id,
                proj.name,
                proj.description,
                proj.scm_type,
                proj.organization_id,
                proj.created,
                proj.modified
            FROM main_project proj
            ORDER BY proj.id ASC
            LIMIT 5
        """,
        ),
        (
            "Hosts",
            """
            SELECT
                h.id AS external_id,
                h.name,
                h.description,
                h.inventory_id,
                h.created,
                h.modified
            FROM main_host h
            WHERE h.enabled = TRUE
            ORDER BY h.id ASC
            LIMIT 5
        """,
        ),
        (
            "Users",
            """
            SELECT
                u.id AS external_id,
                u.username,
                u.first_name,
                u.last_name,
                u.email,
                CASE
                    WHEN u.is_superuser THEN 'superuser'
                    ELSE 'normal'
                END AS user_type,
                u.date_joined AS created,
                u.last_login AS modified
            FROM auth_user u
            WHERE u.is_active = TRUE
            ORDER BY u.id ASC
            LIMIT 5
        """,
        ),
        (
            "Execution Environments",
            """
            SELECT
                ee.id AS external_id,
                ee.name,
                ee.description,
                ee.image,
                ee.created,
                ee.modified
            FROM main_executionenvironment ee
            ORDER BY ee.id ASC
            LIMIT 5
        """,
        ),
        (
            "Instance Groups",
            """
            SELECT
                ig.id AS external_id,
                ig.name,
                ig.is_container_group,
                ig.created,
                ig.modified
            FROM main_instancegroup ig
            ORDER BY ig.id ASC
            LIMIT 5
        """,
        ),
        (
            "Labels",
            """
            SELECT
                l.id AS external_id,
                l.name,
                l.organization_id,
                l.created,
                l.modified
            FROM main_label l
            ORDER BY l.id ASC
            LIMIT 5
        """,
        ),
    ]

    # Run tests
    results = {}
    for test_name, query in tests:
        success = test_query(conn, test_name, query)
        results[test_name] = success

    conn.close()

    # Summary

    passed = sum(1 for v in results.values() if v)
    total = len(results)

    for _test_name, _success in results.items():
        pass

    if passed == total:
        return 0
    else:
        return 1


if __name__ == "__main__":
    import sys

    sys.exit(main())
