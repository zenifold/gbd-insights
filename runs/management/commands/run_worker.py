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
import time

from django.conf import settings
from django.core.management.base import BaseCommand

from runs import queue
from runs.processing import process_run

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
        status = process_run(run)
        if status == "DONE":
            self.stdout.write(self.style.SUCCESS(f"Run {run.id} done"))
        else:
            self.stdout.write(f"Run {run.id} -> {status}")
