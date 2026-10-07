import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("analytics", "0002_analyticscollectionclaim"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="analyticscollectionclaim",
            name="created_by",
            field=models.ForeignKey(
                default=None,
                editable=False,
                help_text="The user who created this resource.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="%(app_label)s_%(class)s_created+",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="analyticscollectionclaim",
            name="modified_by",
            field=models.ForeignKey(
                default=None,
                editable=False,
                help_text="The user who last modified this resource.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="%(app_label)s_%(class)s_modified+",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
