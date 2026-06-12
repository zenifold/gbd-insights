"""
Background worker: claims queued analysis runs and executes the pipeline.

Crash-safe and idempotent — a run is claimed atomically, processed in an
isolated temp dir, and its outcome (DONE/FAILED) is written in a short
transaction. On startup (and periodically) a reaper re-queues runs orphaned by a
crashed worker. Designed to run as a separate Render service from the same image.
"""
from __future__ import annotations

import logging
import os
import signal
import socket
import tempfile
import time
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from pipeline import run_pipeline
from runs import queue
from runs.models import RunStatus
from runs.storage import get_storage
from runs.validation import validate_upload

log = logging.getLogger("runs.worker")


class Command(BaseCommand):
    help = "Run the analysis background worker loop."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true",
                            help="Process at most one run then exit (useful for tests/cron).")

    def handle(self, *args, **options):
        worker_id = f"{socket.gethostname()}:{os.getpid()}"
        self._stop = False

        def _signal(_signum, _frame):
            self.stdout.write("Shutdown requested; finishing current run…")
            self._stop = True

        signal.signal(signal.SIGINT, _signal)
        signal.signal(signal.SIGTERM, _signal)

        self.stdout.write(f"Worker {worker_id} starting.")
        self._reap()

        last_reap = time.monotonic()
        while not self._stop:
            run = queue.claim_next_run(worker_id)
            if run is None:
                if options["once"]:
                    self.stdout.write("Queue empty; exiting (--once).")
                    return
                time.sleep(settings.WORKER_POLL_INTERVAL)
                if time.monotonic() - last_reap > settings.WORKER_STALE_SECONDS:
                    self._reap()
                    last_reap = time.monotonic()
                continue

            self._process(run)
            if options["once"]:
                return

        self.stdout.write("Worker stopped.")

    # ----------------------------------------------------------------------
    def _reap(self):
        requeued, failed = queue.requeue_stale(
            settings.WORKER_STALE_SECONDS, settings.WORKER_MAX_ATTEMPTS
        )
        if requeued or failed:
            self.stdout.write(f"Reaper: re-queued {requeued}, failed {failed} stale run(s).")

    def _process(self, run):
        self.stdout.write(f"Processing run {run.id} (attempt {run.attempts})…")
        storage = get_storage()
        workdir = Path(tempfile.mkdtemp(prefix=f"gbd-run-{run.id}-"))
        try:
            source = workdir / (Path(run.source_filename).name or "source")
            storage.download_to(run.source_path, source)

            result = validate_upload(source, run.source_filename, run.source_bytes or source.stat().st_size)
            if not result.ok:
                queue.mark_failed(run.id, result.error_code, result.message)
                self.stdout.write(f"Run {run.id} failed validation: {result.error_code}")
                return

            outcome = run_pipeline(source, workdir / "out")
            artifact_name = outcome.artifact_path.name
            content_type = "application/zip" if artifact_name.endswith(".zip") else "application/pdf"
            artifact_path = f"artifacts/{run.client.slug}/{run.id}/{artifact_name}"
            storage.upload_file(artifact_path, outcome.artifact_path, content_type=content_type)
            summary = dict(outcome.summary)
            summary["warnings"] = outcome.warnings
            queue.mark_done(run.id, artifact_path, summary=summary)
            self.stdout.write(self.style.SUCCESS(f"Run {run.id} done -> {artifact_path}"))
        except Exception:  # noqa: BLE001 — worker must never crash on a single run
            log.exception("Run %s crashed", run.id)
            queue.mark_failed(
                run.id,
                "pipeline_error",
                "An unexpected error occurred while analyzing this file. "
                "Our team has been notified; please try again or contact support.",
            )
        finally:
            self._cleanup(workdir)

    @staticmethod
    def _cleanup(workdir: Path):
        import shutil

        shutil.rmtree(workdir, ignore_errors=True)
