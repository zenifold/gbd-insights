from datetime import timedelta

from django.utils import timezone

from runs import queue
from runs.models import AnalysisRun, RunStatus


def _make_run(client, **kwargs):
    defaults = dict(client=client, status=RunStatus.QUEUED, source_path="uploads/x", source_bytes=10)
    defaults.update(kwargs)
    return AnalysisRun.objects.create(**defaults)


def test_claim_returns_one_then_empty(demo_client):
    run = _make_run(demo_client)

    claimed = queue.claim_next_run("worker-1")
    assert claimed is not None and claimed.id == run.id
    assert claimed.status == RunStatus.RUNNING
    assert claimed.attempts == 1
    assert claimed.claimed_by == "worker-1"

    # Nothing else queued.
    assert queue.claim_next_run("worker-2") is None


def test_claim_is_fifo(demo_client):
    older = _make_run(demo_client, source_path="a")
    newer = _make_run(demo_client, source_path="b")
    # Force a deterministic ordering on created_at.
    AnalysisRun.objects.filter(id=older.id).update(
        created_at=timezone.now() - timedelta(minutes=5)
    )
    claimed = queue.claim_next_run("w")
    assert claimed.id == older.id


def test_mark_done_and_failed(demo_client):
    run = _make_run(demo_client)
    queue.mark_done(run.id, "artifacts/x/report.pdf")
    run.refresh_from_db()
    assert run.status == RunStatus.DONE
    assert run.artifact_path == "artifacts/x/report.pdf"
    assert run.finished_at is not None

    run2 = _make_run(demo_client)
    queue.mark_failed(run2.id, "bad_extension", "Unsupported file.")
    run2.refresh_from_db()
    assert run2.status == RunStatus.FAILED
    assert run2.error_code == "bad_extension"


def test_reaper_requeues_stale_running(demo_client):
    run = _make_run(
        demo_client,
        status=RunStatus.RUNNING,
        attempts=1,
        claimed_by="dead",
        claimed_at=timezone.now() - timedelta(hours=1),
    )
    requeued, failed = queue.requeue_stale(stale_seconds=60, max_attempts=3)
    assert (requeued, failed) == (1, 0)
    run.refresh_from_db()
    assert run.status == RunStatus.QUEUED
    assert run.claimed_by == ""


def test_reaper_fails_poison_messages(demo_client):
    run = _make_run(
        demo_client,
        status=RunStatus.RUNNING,
        attempts=3,
        claimed_at=timezone.now() - timedelta(hours=1),
    )
    requeued, failed = queue.requeue_stale(stale_seconds=60, max_attempts=3)
    assert (requeued, failed) == (0, 1)
    run.refresh_from_db()
    assert run.status == RunStatus.FAILED
    assert run.error_code == "stuck"
