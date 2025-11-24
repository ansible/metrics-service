# Generated migration to remove source field from Setting model

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0009_alter_setting_options_remove_setting_ip_address"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="setting",
            name="source",
        ),
    ]


