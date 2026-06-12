"""
Helpers for establishing the Postgres Row Level Security (RLS) context.

RLS policies (see migration 0002) deny all access by default and only permit
rows when a request-scoped GUC is set:

  * ``app.scope = 'service'``      -> trusted server context, full access.
  * ``app.client_id = '<uuid>'``   -> access limited to a single client's rows.

The values are set with ``set_config(name, value, is_local => true)``, which is
the function form of ``SET LOCAL`` — scoped to the current transaction so it can
never leak across requests on a pooled/persistent connection.
"""
from __future__ import annotations

from contextlib import contextmanager

from django.db import connection, transaction


def set_service_scope(cursor) -> None:
    """Grant the trusted-server scope on the current transaction."""
    cursor.execute("SELECT set_config('app.scope', 'service', true)")


def set_client_scope(cursor, client_id) -> None:
    """Limit visibility to a single client on the current transaction."""
    cursor.execute("SELECT set_config('app.scope', '', true)")
    cursor.execute("SELECT set_config('app.client_id', %s, true)", [str(client_id)])


@contextmanager
def service_scope():
    """
    Open a transaction with the trusted-server RLS scope set.

    Use in non-request contexts (e.g. the worker, management commands) where no
    middleware has established a scope.
    """
    with transaction.atomic():
        with connection.cursor() as cursor:
            set_service_scope(cursor)
        yield
