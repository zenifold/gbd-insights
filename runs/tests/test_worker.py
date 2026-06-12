from django.core.management import call_command

from runs.models import AnalysisRun, RunStatus
from runs.storage import get_storage


def _queue_with_source(demo_client, content: bytes, filename: str, tmp_path):
    run = AnalysisRun.objects.create(
        client=demo_client, status=RunStatus.QUEUED, source_filename=filename
    )
    ext = "." + filename.rsplit(".", 1)[-1]
    run.source_path = f"uploads/{demo_client.slug}/{run.id}/source{ext}"
    run.source_bytes = len(content)
    run.save()

    src = tmp_path / filename
    src.write_bytes(content)
    get_storage().upload_file(run.source_path, src)
    return run


def test_worker_happy_path(demo_client, sample_csv_bytes, tmp_path):
    run = _queue_with_source(demo_client, sample_csv_bytes, "sample.csv", tmp_path)

    call_command("run_worker", "--once")

    run.refresh_from_db()
    assert run.status == RunStatus.DONE
    assert run.artifact_path.endswith("report_bundle.zip")
    assert get_storage().stat(run.artifact_path).exists
    # Summary is persisted for the status page.
    assert run.summary["line_items"] == 8
    assert run.summary["top_category"] == "Beef"
    assert run.summary["total_emissions_kgco2e"] > 0
    assert "warnings" in run.summary


def test_worker_fails_validation_with_human_message(demo_client, tmp_path):
    run = _queue_with_source(demo_client, b"not a real spreadsheet", "notes.txt", tmp_path)

    call_command("run_worker", "--once")

    run.refresh_from_db()
    assert run.status == RunStatus.FAILED
    assert run.error_code == "bad_extension"
    assert run.error_message  # human-readable, non-empty
    assert not run.artifact_path


def test_worker_marks_failed_on_pipeline_crash(demo_client, sample_csv_bytes, tmp_path, monkeypatch):
    run = _queue_with_source(demo_client, sample_csv_bytes, "sample.csv", tmp_path)

    def boom(*args, **kwargs):
        raise RuntimeError("kaboom")

    monkeypatch.setattr("runs.processing.run_pipeline", boom)

    call_command("run_worker", "--once")

    run.refresh_from_db()
    assert run.status == RunStatus.FAILED
    assert run.error_code == "pipeline_error"
    assert "stack" not in run.error_message.lower()  # no traceback leaked to the UI
