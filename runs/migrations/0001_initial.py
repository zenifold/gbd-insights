import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Client",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=255)),
                ("slug", models.SlugField(max_length=255, unique=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"db_table": "runs_client", "ordering": ["name"]},
        ),
        migrations.CreateModel(
            name="AnalysisRun",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_by", models.CharField(blank=True, default="", max_length=150)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("PENDING_UPLOAD", "Awaiting upload"),
                            ("QUEUED", "Queued"),
                            ("RUNNING", "Running"),
                            ("DONE", "Done"),
                            ("FAILED", "Failed"),
                        ],
                        default="PENDING_UPLOAD",
                        max_length=20,
                    ),
                ),
                ("source_path", models.CharField(blank=True, default="", max_length=1024)),
                ("source_filename", models.CharField(blank=True, default="", max_length=512)),
                ("source_bytes", models.BigIntegerField(blank=True, null=True)),
                ("artifact_path", models.CharField(blank=True, default="", max_length=1024)),
                ("error_code", models.CharField(blank=True, default="", max_length=64)),
                ("error_message", models.TextField(blank=True, default="")),
                ("attempts", models.PositiveIntegerField(default=0)),
                ("claimed_by", models.CharField(blank=True, default="", max_length=128)),
                ("claimed_at", models.DateTimeField(blank=True, null=True)),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "client",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="runs",
                        to="runs.client",
                    ),
                ),
            ],
            options={"db_table": "runs_analysisrun", "ordering": ["-created_at"]},
        ),
        migrations.AddIndex(
            model_name="analysisrun",
            index=models.Index(fields=["status", "created_at"], name="run_status_created_idx"),
        ),
    ]
