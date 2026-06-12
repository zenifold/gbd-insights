"""
Postgres-backed job queue operations.

The ``runs_analysisrun`` table *is* the queue. A worker claims the oldest queued
run atomically with ``FOR UPDATE SKIP LOCKED`` so multiple workers never pick the
same row. Every operation runs in its own short transaction under the trusted
``service`` RLS scope.
"""
from __future__ import annotations

from django.db import connection, transaction
from django.utils import timezone

from runs.db import set_service_scope
from runs.models import AnalysisRun, RunStatus

CLAIM_SQL = """
UPDATE runs_analysisrun
SET status = 'RUNNING',
    claimed_by = %s,
    claimed_at = now(),
    started_at = now(),
    attempts = attempts + 1,
    updated_at = now()
WHERE id = (
    SELECT id FROM runs_analysisrun
    WHERE status = 'QUEUED'
    ORDER BY created_at
    FOR UPDATE SKIP LOCKED
    LIMIT 1
)
RETURNING id
"""


def claim_next_run(worker_id: str) -> AnalysisRun | None:
    """Atomically claim the oldest queued run, or return None if the queue is empty."""
    with transaction.atomic():
        with connection.cursor() as cursor:
            set_service_scope(cursor)
            cursor.execute(CLAIM_SQL, [worker_id])
            row = cursor.fetchone()
        if row is None:
            return None
        return AnalysisRun.objects.select_related("client").get(id=row[0])


def set_progress(run_id, percent: int, message: str = "") -> None:
    """Record live pipeline progress (0–100) for the status page to poll."""
    percent = max(0, min(100, int(percent)))
    with transaction.atomic():
        with connection.cursor() as cursor:
            set_service_scope(cursor)
        AnalysisRun.objects.filter(id=run_id).update(
            progress=percent, progress_message=message[:120], updated_at=timezone.now()
        )


def mark_done(run_id, artifact_path: str, summary: dict | None = None) -> None:
    with transaction.atomic():
        with connection.cursor() as cursor:
            set_service_scope(cursor)
        AnalysisRun.objects.filter(id=run_id).update(
            status=RunStatus.DONE,
            artifact_path=artifact_path,
            summary=summary or {},
            progress=100,
            progress_message="Complete",
            error_code="",
            error_message="",
            finished_at=timezone.now(),
            updated_at=timezone.now(),
        )


def mark_failed(run_id, error_code: str, message: str) -> None:
    with transaction.atomic():
        with connection.cursor() as cursor:
            set_service_scope(cursor)
        AnalysisRun.objects.filter(id=run_id).update(
            status=RunStatus.FAILED,
            error_code=error_code,
            error_message=message,
            finished_at=timezone.now(),
            updated_at=timezone.now(),
        )


def requeue_stale(stale_seconds: int, max_attempts: int) -> tuple[int, int]:
    """
    Recover runs orphaned by a crashed worker.

    Runs stuck in RUNNING past ``stale_seconds`` are re-queued, unless they have
    already used up ``max_attempts`` (poison messages) — those are failed with a
    human-readable message. Returns ``(requeued, failed)``.
    """
    with transaction.atomic():
        with connection.cursor() as cursor:
            set_service_scope(cursor)
            cursor.execute(
                """
                UPDATE runs_analysisrun
                SET status = 'FAILED',
                    error_code = 'stuck',
                    error_message = %s,
                    finished_at = now(),
                    updated_at = now()
                WHERE status = 'RUNNING'
                  AND claimed_at < now() - make_interval(secs => %s)
                  AND attempts >= %s
                """,
                [
                    "This analysis did not complete after several attempts. "
                    "Please try re-uploading the file.",
                    stale_seconds,
                    max_attempts,
                ],
            )
            failed = cursor.rowcount
            cursor.execute(
                """
                UPDATE runs_analysisrun
                SET status = 'QUEUED',
                    claimed_by = '',
                    claimed_at = NULL,
                    started_at = NULL,
                    updated_at = now()
                WHERE status = 'RUNNING'
                  AND claimed_at < now() - make_interval(secs => %s)
                  AND attempts < %s
                """,
                [stale_seconds, max_attempts],
            )
            requeued = cursor.rowcount
    return requeued, failed
