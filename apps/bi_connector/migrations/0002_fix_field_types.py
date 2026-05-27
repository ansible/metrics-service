from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("bi_connector", "0001_stored_collection"),
    ]

    operations = [
        migrations.AlterField(
            model_name="collectionbatch",
            name="records_imported",
            field=models.PositiveBigIntegerField(default=0),
        ),
        migrations.AlterField(
            model_name="storedhostmetric",
            name="host_id",
            field=models.BigIntegerField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="storedjobhostsummary",
            name="summary_id",
            field=models.BigIntegerField(db_index=True, unique=True),
        ),
        migrations.AlterField(
            model_name="storedjobhostsummary",
            name="host_id",
            field=models.BigIntegerField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="storedjobhostsummary",
            name="job_id",
            field=models.BigIntegerField(blank=True, db_index=True, null=True),
        ),
        migrations.AlterField(
            model_name="storedjobhostsummary",
            name="organization_id",
            field=models.BigIntegerField(blank=True, db_index=True, null=True),
        ),
        migrations.AlterField(
            model_name="storedjobhostsummary",
            name="inventory_id",
            field=models.BigIntegerField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="storedindirectaudit",
            name="audit_id",
            field=models.BigIntegerField(db_index=True, unique=True),
        ),
        migrations.AlterField(
            model_name="storedindirectaudit",
            name="host_id",
            field=models.BigIntegerField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="storedindirectaudit",
            name="job_id",
            field=models.BigIntegerField(blank=True, db_index=True, null=True),
        ),
        migrations.AlterField(
            model_name="storedindirectaudit",
            name="organization_id",
            field=models.BigIntegerField(blank=True, db_index=True, null=True),
        ),
    ]
