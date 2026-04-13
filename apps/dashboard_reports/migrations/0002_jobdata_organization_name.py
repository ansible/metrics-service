from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("dashboard_reports", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="jobdata",
            name="organization_name",
            field=models.CharField(
                blank=True,
                help_text="Organization name for display (from AWX)",
                max_length=512,
                null=True,
            ),
        ),
    ]
