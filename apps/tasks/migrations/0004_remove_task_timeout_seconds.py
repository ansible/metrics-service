from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('tasks', '0003_remove_anonymizedmetricspayload_unique_active_payload_per_summary_and_more'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='task',
            name='timeout_seconds',
        ),
    ]
