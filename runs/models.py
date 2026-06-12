import uuid

from django.conf import settings
from django.db import models


class Client(models.Model):
    """An institution whose procurement data is analyzed. Unit of RLS isolation."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "runs_client"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Profile(models.Model):
    """
    Links a Django user to the client (institution) they act for.

    ``client`` set  -> a client self-serve user, scoped to that one institution.
    ``client`` null -> a GBD staff user (also ``user.is_staff``), who sees all.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile"
    )
    client = models.ForeignKey(
        Client, on_delete=models.PROTECT, null=True, blank=True, related_name="members"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "runs_profile"

    def __str__(self):
        return f"{self.user} → {self.client or 'GBD staff'}"


class Tag(models.Model):
    """A sector/category label (e.g. Healthcare, Academic, Corporate) for a run."""

    slug = models.SlugField(max_length=50, unique=True)
    name = models.CharField(max_length=50)

    class Meta:
        db_table = "runs_tag"
        ordering = ["name"]

    def __str__(self):
        return self.name


class RunStatus(models.TextChoices):
    PENDING_UPLOAD = "PENDING_UPLOAD", "Awaiting upload"
    QUEUED = "QUEUED", "Queued"
    RUNNING = "RUNNING", "Running"
    DONE = "DONE", "Done"
    FAILED = "FAILED", "Failed"


# States from which a request can still legitimately be retried/queued by a worker.
ACTIVE_STATES = {RunStatus.QUEUED, RunStatus.RUNNING}
TERMINAL_STATES = {RunStatus.DONE, RunStatus.FAILED}


class AnalysisRun(models.Model):
    """A single analysis job: the queue row and the audit record."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    client = models.ForeignKey(Client, on_delete=models.PROTECT, related_name="runs")
    created_by = models.CharField(max_length=150, blank=True, default="")
    tags = models.ManyToManyField(Tag, blank=True, related_name="runs")

    status = models.CharField(
        max_length=20, choices=RunStatus.choices, default=RunStatus.PENDING_UPLOAD
    )

    # Live processing progress (0–100) + a human-readable stage label, updated by
    # the pipeline as it runs so the status page can show a real progress bar.
    progress = models.PositiveSmallIntegerField(default=0)
    progress_message = models.CharField(max_length=120, blank=True, default="")

    # Source upload (lives in object storage, never on the web dyno).
    source_path = models.CharField(max_length=1024, blank=True, default="")
    source_filename = models.CharField(max_length=512, blank=True, default="")
    source_bytes = models.BigIntegerField(null=True, blank=True)

    # Produced report artifact.
    artifact_path = models.CharField(max_length=1024, blank=True, default="")
    # Headline pipeline summary (totals, top category, warnings) for the UI.
    summary = models.JSONField(default=dict, blank=True)

    # Failure reporting — human-readable message shown in the UI; code for tests/ops.
    error_code = models.CharField(max_length=64, blank=True, default="")
    error_message = models.TextField(blank=True, default="")

    # Worker bookkeeping (crash-safety / idempotency).
    attempts = models.PositiveIntegerField(default=0)
    claimed_by = models.CharField(max_length=128, blank=True, default="")
    claimed_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "runs_analysisrun"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "created_at"], name="run_status_created_idx"),
        ]

    def __str__(self):
        return f"Run {self.id} [{self.status}]"

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_STATES
