from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("tasks", "0004_remove_task_timeout_seconds"),
    ]

    operations = [
        migrations.AddField(
            model_name="task",
            name="request_id",
            field=models.CharField(
                blank=True,
                db_index=True,
                editable=False,
                help_text="request_id of the API call that created this task",
                max_length=36,
                null=True,
            ),
        ),
    ]
