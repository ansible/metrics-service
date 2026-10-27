from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("dashboard_reports", "0003_add_dashboard_collection_telemetry"),
    ]

    operations = [
        migrations.AddField(
            model_name="jobdata",
            name="job_type",
            field=models.CharField(
                blank=True,
                help_text="Controller unified-job model name (for example, job or systemjob)",
                max_length=50,
                null=True,
            ),
        ),
        migrations.AddIndex(
            model_name="jobdata",
            index=models.Index(fields=["job_type", "finished"], name="dashboard_jd_type_finished_idx"),
        ),
    ]
