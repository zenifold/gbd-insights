from django.test import Client as DjangoClient

from runs.models import AnalysisRun, Client, RunStatus


def _run(client, **kw):
    return AnalysisRun.objects.create(client=client, **kw)


def test_dashboard_requires_login(client):
    resp = client.get("/dashboard")
    assert resp.status_code == 302 and "/login" in resp["Location"]


def test_staff_sees_all_clients_runs(staff_client, demo_client):
    other = Client.objects.create(name="Other Co", slug="other-co")
    _run(demo_client, source_filename="mine.csv", status=RunStatus.DONE)
    _run(other, source_filename="theirs.csv", status=RunStatus.FAILED)

    body = staff_client.get("/dashboard").content.decode()
    assert "mine.csv" in body and "theirs.csv" in body
    assert "Other Co" in body


# --- The multi-tenant isolation guarantees ---
def test_client_user_sees_only_their_runs(tenant_client, demo_client):
    other = Client.objects.create(name="Other Co", slug="other-co")
    _run(demo_client, source_filename="mine.csv", status=RunStatus.DONE)
    _run(other, source_filename="theirs.csv", status=RunStatus.DONE)

    body = tenant_client.get("/dashboard").content.decode()
    assert "mine.csv" in body
    assert "theirs.csv" not in body
    assert "Other Co" not in body


def test_client_cannot_open_another_clients_run(tenant_client):
    other = Client.objects.create(name="Other Co", slug="other-co")
    run = _run(other, status=RunStatus.DONE, artifact_path="artifacts/o/report_bundle.zip")
    assert tenant_client.get(f"/runs/{run.id}/status").status_code == 404
    assert tenant_client.get(f"/runs/{run.id}/download").status_code == 404
    assert tenant_client.get(f"/runs/{run.id}/status/").status_code in (404, 301)


def test_client_upload_autoscopes_to_their_client(tenant_client, demo_client):
    resp = tenant_client.post("/runs", {"filename": "x.csv", "content_type": "text/csv"})
    assert resp.status_code == 200
    run = AnalysisRun.objects.get(id=resp.json()["run_id"])
    assert run.client_id == demo_client.id
    assert run.created_by == "clientu"


def test_run_detail_and_source_are_staff_only(gbd_user, client_user, demo_client, sample_csv_bytes, tmp_path):
    from runs.storage import get_storage

    run = _run(
        demo_client, source_filename="s.csv", source_path="uploads/demo/s.csv",
        status=RunStatus.DONE, summary={"top_category": "Beef"},
    )
    src = tmp_path / "s.csv"
    src.write_bytes(sample_csv_bytes)
    get_storage().upload_file(run.source_path, src)

    staff = DjangoClient(); staff.force_login(gbd_user)
    tenant = DjangoClient(); tenant.force_login(client_user)

    # client user: admin views are hidden
    assert tenant.get(f"/dashboard/runs/{run.id}").status_code == 404
    assert tenant.get(f"/dashboard/runs/{run.id}/source").status_code == 404
    # staff: full access
    assert staff.get(f"/dashboard/runs/{run.id}").status_code == 200
    r = staff.get(f"/dashboard/runs/{run.id}/source")
    assert r.status_code == 302 and "/_storage/download" in r["Location"]
