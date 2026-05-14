from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="PrometheusSnapshot",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("modified", models.DateTimeField(auto_now=True, help_text="The date/time this resource was created.")),
                ("created", models.DateTimeField(auto_now_add=True, help_text="The date/time this resource was created.")),
                (
                    "service",
                    models.CharField(
                        choices=[("controller", "Controller"), ("eda", "EDA"), ("hub", "Hub")],
                        db_index=True,
                        help_text="The AAP service that was scraped",
                        max_length=50,
                    ),
                ),
                ("scraped_at", models.DateTimeField(db_index=True, help_text="Timestamp when the scrape was initiated")),
                (
                    "status",
                    models.CharField(
                        choices=[("ok", "OK"), ("error", "Error")],
                        default="ok",
                        help_text="Whether the scrape succeeded",
                        max_length=20,
                    ),
                ),
                (
                    "http_status",
                    models.IntegerField(blank=True, help_text="HTTP response code returned by the target", null=True),
                ),
                (
                    "raw_text",
                    models.TextField(blank=True, default="", help_text="Raw Prometheus exposition format text"),
                ),
                ("byte_count", models.IntegerField(default=0, help_text="Size of raw_text in bytes")),
                (
                    "error_message",
                    models.TextField(blank=True, default="", help_text="Error details if status is 'error'"),
                ),
            ],
            options={
                "ordering": ["-scraped_at"],
            },
        ),
        migrations.AddIndex(
            model_name="prometheussnapshot",
            index=models.Index(fields=["service", "scraped_at"], name="prometheus__service_idx"),
        ),
    ]
