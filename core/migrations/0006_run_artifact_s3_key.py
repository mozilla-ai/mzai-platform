# Generated by Django 4.2.20 on 2025-05-21 15:34

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0005_run_run_url'),
    ]

    operations = [
        migrations.AddField(
            model_name='run',
            name='artifact_s3_key',
            field=models.CharField(blank=True, max_length=1024, null=True),
        ),
    ]
