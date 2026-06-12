from urllib.parse import urlsplit

from runs.models import AnalysisRun, RunStatus


def test_requires_login(client):
    resp = client.get("/")
    assert resp.status_code == 302
    assert "/login" in resp["Location"]


def test_upload_page_renders_for_staff(staff_client):
    resp = staff_client.get("/")
    assert resp.status_code == 200
    assert b"Upload" in resp.content


def test_two_step_upload_flow(staff_client, demo_client, sample_csv_bytes):
    # Step 1 — staff create run for a chosen client + signed upload URL.
    resp = staff_client.post(
        "/runs",
        {"client_id": str(demo_client.id), "filename": "sample.csv", "content_type": "text/csv"},
    )
    assert resp.status_code == 200, resp.content
    data = resp.json()
    run = AnalysisRun.objects.get(id=data["run_id"])
    assert run.status == RunStatus.PENDING_UPLOAD
    assert run.created_by == "gbd"

    # Step 2 — PUT bytes to the (local) signed storage endpoint.
    target = urlsplit(data["upload"]["url"])
    resp = staff_client.put(
        f"{target.path}?{target.query}", data=sample_csv_bytes, content_type="text/csv"
    )
    assert resp.status_code == 200

    # Step 3 — finalize queues the run.
    resp = staff_client.post(data["finalize_url"])
    assert resp.status_code == 200
    assert resp.json()["status"] == RunStatus.QUEUED


def test_staff_creates_client_by_name_with_tags(staff_client):
    from runs.models import Client

    resp = staff_client.post(
        "/runs",
        {"filename": "x.csv", "content_type": "text/csv",
         "client_name": "Memorial Hospital", "tags": ["healthcare", "corporate"]},
    )
    assert resp.status_code == 200, resp.content
    run = AnalysisRun.objects.get(id=resp.json()["run_id"])
    assert run.client.name == "Memorial Hospital"
    assert run.client.slug == "memorial-hospital"
    assert set(run.tags.values_list("slug", flat=True)) == {"healthcare", "corporate"}
    assert Client.objects.filter(slug="memorial-hospital").exists()  # created on the fly


def test_staff_blank_client_name_uses_ad_hoc(staff_client):
    resp = staff_client.post("/runs", {"filename": "x.csv", "content_type": "text/csv"})
    run = AnalysisRun.objects.get(id=resp.json()["run_id"])
    assert run.client.slug == "ad-hoc"


def test_create_run_rejects_bad_extension(staff_client, demo_client):
    resp = staff_client.post(
        "/runs", {"client_id": str(demo_client.id), "filename": "notes.txt"}
    )
    assert resp.status_code == 400


def test_finalize_fails_when_no_file(staff_client, demo_client):
    resp = staff_client.post(
        "/runs", {"client_id": str(demo_client.id), "filename": "sample.csv"}
    )
    resp = staff_client.post(resp.json()["finalize_url"])
    assert resp.status_code == 400
    assert "didn't receive" in resp.json()["error"]


def test_download_404_when_not_done(staff_client, demo_client):
    run = AnalysisRun.objects.create(client=demo_client, status=RunStatus.QUEUED)
    assert staff_client.get(f"/runs/{run.id}/download").status_code == 404


def test_template_csv_download(staff_client):
    from django.test import Client as DjangoClient

    assert DjangoClient().get("/template.csv").status_code == 302  # anonymous → login
    resp = staff_client.get("/template.csv")
    assert resp.status_code == 200
    assert resp["Content-Type"] == "text/csv"
    assert b"product,vendor,spend,quantity,unit,date" in resp.content


def test_status_page_shows_metrics_when_done(staff_client, demo_client):
    run = AnalysisRun.objects.create(
        client=demo_client,
        status=RunStatus.DONE,
        artifact_path="artifacts/x/report_bundle.zip",
        summary={"total_emissions_tonnes": 7.8, "total_emissions_kgco2e": 7800,
                 "top_category": "Beef", "top_category_share_pct": 70,
                 "line_items": 8, "emissions_intensity_kgco2e_per_usd": 1.97,
                 "warnings": ["No usable date column was found."]},
    )
    body = staff_client.get(f"/runs/{run.id}/status").content.decode()
    assert "Beef" in body and "CO₂e" in body  # metrics rendered
    assert "No usable date column" in body     # caveat surfaced


def test_inline_processing_on_finalize(staff_client, demo_client, sample_csv_bytes, settings):
    settings.PROCESS_INLINE = True  # free single-service mode
    resp = staff_client.post(
        "/runs",
        {"client_id": str(demo_client.id), "filename": "sample.csv", "content_type": "text/csv"},
    )
    data = resp.json()
    target = urlsplit(data["upload"]["url"])
    staff_client.put(f"{target.path}?{target.query}", data=sample_csv_bytes, content_type="text/csv")

    resp = staff_client.post(data["finalize_url"])
    assert resp.json()["status"] == "DONE"  # processed inline, no worker

    run = AnalysisRun.objects.get(id=data["run_id"])
    assert run.status == "DONE"
    assert run.artifact_path.endswith("report_bundle.zip")
    assert run.summary["top_category"] == "Beef"


def test_storage_upload_rejects_bad_signature(client):
    resp = client.put(
        "/_storage/upload?path=uploads/x&exp=9999999999&sig=bad",
        data=b"x",
        content_type="text/csv",
    )
    assert resp.status_code == 404
