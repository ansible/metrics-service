import uuid

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tasks", "0004_remove_task_timeout_seconds"),
    ]

    operations = [
        migrations.AddField(
            model_name="task",
            name="trace_id",
            field=models.UUIDField(
                default=uuid.uuid4,
                editable=False,
                db_index=True,
                help_text="Unique trace identifier for correlating logs across scheduler → dispatcherd → collector",
            ),
        ),
    ]
