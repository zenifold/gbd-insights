"""
Shared run processing — used by both the dedicated worker (`run_worker`) and the
inline path (finalize, when PROCESS_INLINE is on for free single-service hosting).
"""
from __future__ import annotations

import importlib
import inspect
import logging
import shutil
import tempfile
from functools import lru_cache
from pathlib import Path

from django.conf import settings

from runs import queue
from runs.storage import get_storage
from runs.validation import validate_upload

log = logging.getLogger("runs.processing")


@lru_cache(maxsize=1)
def _get_pipeline():
    """
    Resolve the configured analysis pipeline callable (settings.PIPELINE_CALLABLE).
    Lets GBD swap in their own Python — anything matching
    ``fn(input_path, out_dir, *, on_progress=None) -> PipelineResult`` — by
    setting one env var, no app code changes.
    """
    dotted = getattr(settings, "PIPELINE_CALLABLE", "pipeline.run_pipeline")
    module_path, _, attr = dotted.rpartition(".")
    fn = getattr(importlib.import_module(module_path), attr)
    try:
        accepts_progress = "on_progress" in inspect.signature(fn).parameters
    except (TypeError, ValueError):  # builtins / C callables aren't introspectable
        accepts_progress = False
    return fn, accepts_progress


def process_run(run) -> str:
    """
    Execute the pipeline for a single claimed (RUNNING) run; marks it DONE or
    FAILED. Never raises — a failed run is recorded with a human-readable message.
    Returns the terminal status.
    """
    storage = get_storage()
    workdir = Path(tempfile.mkdtemp(prefix=f"gbd-run-{run.id}-"))
    try:
        source = workdir / (Path(run.source_filename).name or "source")
        storage.download_to(run.source_path, source)

        result = validate_upload(
            source, run.source_filename, run.source_bytes or source.stat().st_size
        )
        if not result.ok:
            queue.mark_failed(run.id, result.error_code, result.message)
            return "FAILED"

        queue.set_progress(run.id, 4, "Starting analysis")

        def _on_progress(percent: int, message: str) -> None:
            queue.set_progress(run.id, percent, message)

        pipeline_fn, accepts_progress = _get_pipeline()
        kwargs = {"on_progress": _on_progress} if accepts_progress else {}
        outcome = pipeline_fn(source, workdir / "out", **kwargs)
        artifact_name = outcome.artifact_path.name
        content_type = "application/zip" if artifact_name.endswith(".zip") else "application/pdf"
        artifact_path = f"artifacts/{run.client.slug}/{run.id}/{artifact_name}"
        storage.upload_file(artifact_path, outcome.artifact_path, content_type=content_type)
        summary = dict(outcome.summary)
        summary["warnings"] = outcome.warnings
        queue.mark_done(run.id, artifact_path, summary=summary)
        return "DONE"
    except Exception:  # noqa: BLE001 — a single run must never crash the caller
        log.exception("Run %s crashed", run.id)
        queue.mark_failed(
            run.id,
            "pipeline_error",
            "An unexpected error occurred while analyzing this file. "
            "Please try again or contact support.",
        )
        return "FAILED"
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def drain_queue(worker_id: str) -> int:
    """Claim and process every currently-queued run; returns how many were processed."""
    processed = 0
    while True:
        run = queue.claim_next_run(worker_id)
        if run is None:
            break
        process_run(run)
        processed += 1
    return processed
