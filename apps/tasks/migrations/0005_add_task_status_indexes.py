from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tasks", "0004_remove_task_timeout_seconds"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="task",
            index=models.Index(fields=["status"], name="tasks_task_status_idx"),
        ),
        migrations.AddIndex(
            model_name="task",
            index=models.Index(fields=["status", "attempts"], name="tasks_task_status_attempts_idx"),
        ),
        migrations.AddIndex(
            model_name="taskexecution",
            index=models.Index(fields=["task", "status"], name="tasks_te_task_status_idx"),
        ),
    ]
