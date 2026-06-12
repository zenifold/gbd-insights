import pytest
from django.db import connection


@pytest.fixture(autouse=True)
def _rls_service_scope(db):
    """
    Establish the trusted RLS scope for the test transaction so fixtures and the
    ORM can read/write rows (FORCE RLS denies everything by default). View tests
    that exercise per-tenant scoping go through the middleware, which sets its own
    scope per request.
    """
    with connection.cursor() as cur:
        cur.execute("SELECT set_config('app.scope', 'service', true)")
    yield


@pytest.fixture
def demo_client():
    from runs.models import Client

    return Client.objects.create(name="Test University", slug="test-university")


@pytest.fixture
def gbd_user():
    from django.contrib.auth.models import User

    return User.objects.create_user("gbd", password="pw", is_staff=True, is_superuser=True)


@pytest.fixture
def client_user(demo_client):
    from django.contrib.auth.models import User

    from runs.models import Profile

    user = User.objects.create_user("clientu", password="pw", is_staff=False)
    Profile.objects.create(user=user, client=demo_client)
    return user


@pytest.fixture
def staff_client(client, gbd_user):
    client.force_login(gbd_user)
    return client


@pytest.fixture
def tenant_client(client, client_user):
    client.force_login(client_user)
    return client
