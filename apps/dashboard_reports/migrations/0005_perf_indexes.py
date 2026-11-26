# Generated for perf/phase1-hot-paths - DB indexes & duplicate fixes
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("dashboard_reports", "0004_jobdata_job_type"),
    ]

    operations = [
        # TemplateMetadata.template_id: unique=True already implies an index; remove redundant db_index
        migrations.AlterField(
            model_name="templatemetadata",
            name="template_id",
            field=models.IntegerField(
                help_text="AWX job template ID (from AWX database main_jobtemplate table)", unique=True
            ),
        ),
        # JobData.job_id: unique=True already implies an index; remove redundant db_index
        migrations.AlterField(
            model_name="jobdata",
            name="job_id",
            field=models.IntegerField(help_text="AWX job ID (from AWX database main_unifiedjob table)", unique=True),
        ),
        # JobData ordering is -started but no index existed; add descending index for ordering
        migrations.AddIndex(
            model_name="jobdata",
            index=models.Index(fields=["-started"], name="jobdata_started_desc_idx"),
        ),
    ]
