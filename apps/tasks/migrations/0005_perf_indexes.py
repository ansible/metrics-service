# Generated for perf/phase1-hot-paths - DB indexes & model fixes
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("tasks", "0004_remove_task_timeout_seconds"),
    ]

    operations = [
        # Task: add 6 indexes covering hot-path queries (ready_to_run, scheduled_tasks, etc.)
        migrations.AddIndex(
            model_name="task",
            index=models.Index(fields=["status", "scheduled_time"], name="task_status_sched_idx"),
        ),
        migrations.AddIndex(
            model_name="task",
            index=models.Index(fields=["status", "started_at"], name="task_status_started_idx"),
        ),
        migrations.AddIndex(
            model_name="task",
            index=models.Index(fields=["is_system_task", "name"], name="task_system_name_idx"),
        ),
        migrations.AddIndex(
            model_name="task",
            index=models.Index(fields=["function_name"], name="task_func_name_idx"),
        ),
        migrations.AddIndex(
            model_name="task",
            index=models.Index(fields=["name"], name="task_name_idx"),
        ),
        migrations.AddIndex(
            model_name="task",
            index=models.Index(fields=["status", "cron_expression"], name="task_status_cron_idx"),
        ),
        # TaskExecution: add 3 indexes for FK+status filtering and ordering
        migrations.AddIndex(
            model_name="taskexecution",
            index=models.Index(fields=["task", "status"], name="taskexec_task_status_idx"),
        ),
        migrations.AddIndex(
            model_name="taskexecution",
            index=models.Index(fields=["status", "started_at"], name="taskexec_status_started_idx"),
        ),
        migrations.AddIndex(
            model_name="taskexecution",
            index=models.Index(fields=["completed_at"], name="taskexec_completed_idx"),
        ),
        # HourlyMetricsCollection: remove duplicate db_index and redundant single-column index,
        # convert unique_together to explicit UniqueConstraint (avoids duplicate index on Postgres)
        migrations.AlterField(
            model_name="hourlymetricscollection",
            name="collection_timestamp",
            field=models.DateTimeField(help_text="When this collection occurred (rounded to hour)"),
        ),
        migrations.AlterUniqueTogether(
            name="hourlymetricscollection",
            unique_together=set(),
        ),
        migrations.RemoveIndex(
            model_name="hourlymetricscollection",
            name="tasks_hourl_collect_7ced30_idx",
        ),
        migrations.RemoveIndex(
            model_name="hourlymetricscollection",
            name="tasks_hourl_collect_1db2f8_idx",
        ),
        migrations.RemoveIndex(
            model_name="hourlymetricscollection",
            name="tasks_hourl_status_beccc2_idx",
        ),
        migrations.AddIndex(
            model_name="hourlymetricscollection",
            index=models.Index(fields=["collector_type", "collection_timestamp"], name="hmc_collector_timestamp_idx"),
        ),
        migrations.AddIndex(
            model_name="hourlymetricscollection",
            index=models.Index(fields=["status"], name="hmc_status_idx"),
        ),
        migrations.AddConstraint(
            model_name="hourlymetricscollection",
            constraint=models.UniqueConstraint(
                fields=("collector_type", "collection_timestamp"),
                name="hmc_collector_timestamp_uniq",
            ),
        ),
        # DailyMetricsSummary: remove redundant db_index on unique field and duplicate Meta index,
        # convert unique_together to UniqueConstraint
        migrations.AlterField(
            model_name="dailymetricssummary",
            name="summary_date",
            field=models.DateField(help_text="Date this summary covers (YYYY-MM-DD)", unique=True),
        ),
        migrations.AlterUniqueTogether(
            name="dailymetricssummary",
            unique_together=set(),
        ),
        migrations.RemoveIndex(
            model_name="dailymetricssummary",
            name="tasks_daily_summary_41c800_idx",
        ),
        migrations.RemoveIndex(
            model_name="dailymetricssummary",
            name="tasks_daily_status_f8be75_idx",
        ),
        migrations.AddIndex(
            model_name="dailymetricssummary",
            index=models.Index(fields=["status"], name="dms_status_idx"),
        ),
        migrations.AddConstraint(
            model_name="dailymetricssummary",
            constraint=models.UniqueConstraint(fields=("summary_date",), name="dailymetrics_summary_date_uniq"),
        ),
        # AnonymizedMetricsPayload: remove duplicate db_index=True when explicit Index already exists
        migrations.AlterField(
            model_name="anonymizedmetricspayload",
            name="summary_date",
            field=models.DateField(help_text="Date this payload covers"),
        ),
        migrations.RemoveIndex(
            model_name="anonymizedmetricspayload",
            name="tasks_anony_status_61cc36_idx",
        ),
        migrations.RemoveIndex(
            model_name="anonymizedmetricspayload",
            name="tasks_anony_summary_7c154e_idx",
        ),
        migrations.AddIndex(
            model_name="anonymizedmetricspayload",
            index=models.Index(fields=["status", "created"], name="amp_status_created_idx"),
        ),
        migrations.AddIndex(
            model_name="anonymizedmetricspayload",
            index=models.Index(fields=["summary_date"], name="amp_summary_date_idx"),
        ),
    ]
