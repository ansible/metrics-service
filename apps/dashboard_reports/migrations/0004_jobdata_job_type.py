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
                db_index=True,
                help_text="Controller unified-job model name (for example, job or system_job)",
                max_length=50,
                null=True,
            ),
        ),
    ]
