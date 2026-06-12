"""Row Level Security enforcement (the security-critical guardrail)."""
from django.db import connection

from runs.models import AnalysisRun, Client, RunStatus


def _set_scope(scope="", client_id=""):
    with connection.cursor() as cur:
        cur.execute("SELECT set_config('app.scope', %s, true)", [scope])
        cur.execute("SELECT set_config('app.client_id', %s, true)", [client_id])


def test_denies_all_without_scope(demo_client):
    AnalysisRun.objects.create(client=demo_client, status=RunStatus.QUEUED)

    _set_scope(scope="", client_id="")  # no trusted scope, no client scope
    assert AnalysisRun.objects.count() == 0
    assert Client.objects.count() == 0


def test_client_scope_isolates_rows():
    a = Client.objects.create(name="A", slug="a")
    b = Client.objects.create(name="B", slug="b")
    AnalysisRun.objects.create(client=a, status=RunStatus.QUEUED)
    AnalysisRun.objects.create(client=b, status=RunStatus.QUEUED)

    _set_scope(scope="", client_id=str(a.id))
    runs = list(AnalysisRun.objects.all())
    assert len(runs) == 1
    assert runs[0].client_id == a.id
    assert {c.id for c in Client.objects.all()} == {a.id}


def test_service_scope_sees_everything():
    a = Client.objects.create(name="A", slug="a")
    b = Client.objects.create(name="B", slug="b")

    _set_scope(scope="service")
    assert Client.objects.count() >= 2
    assert {a.id, b.id}.issubset({c.id for c in Client.objects.all()})
