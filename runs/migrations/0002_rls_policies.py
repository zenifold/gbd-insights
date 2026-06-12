"""
Enable Row Level Security on the data tables (defense-in-depth).

The migration runs as the connecting role (the non-superuser ``gbd_app`` role in
dev / a dedicated Supabase role in prod), which owns these tables. ``FORCE ROW
LEVEL SECURITY`` makes even the table owner subject to the policies, so every
code path must establish an RLS scope (see ``runs/db.py``) before touching rows:

  * ``app.scope = 'service'``    -> trusted server context (web requests, worker).
  * ``app.client_id = '<uuid>'`` -> single-client scoping.

With neither GUC set, ``current_setting(..., true)`` returns NULL and every
policy predicate is false, so the database returns/permits nothing by default.
"""
from django.db import migrations

ENABLE_SQL = """
ALTER TABLE runs_client ENABLE ROW LEVEL SECURITY;
ALTER TABLE runs_client FORCE ROW LEVEL SECURITY;
CREATE POLICY client_access ON runs_client
    USING (
        current_setting('app.scope', true) = 'service'
        OR id::text = current_setting('app.client_id', true)
    )
    WITH CHECK (
        current_setting('app.scope', true) = 'service'
        OR id::text = current_setting('app.client_id', true)
    );

ALTER TABLE runs_analysisrun ENABLE ROW LEVEL SECURITY;
ALTER TABLE runs_analysisrun FORCE ROW LEVEL SECURITY;
CREATE POLICY run_access ON runs_analysisrun
    USING (
        current_setting('app.scope', true) = 'service'
        OR client_id::text = current_setting('app.client_id', true)
    )
    WITH CHECK (
        current_setting('app.scope', true) = 'service'
        OR client_id::text = current_setting('app.client_id', true)
    );
"""

DISABLE_SQL = """
DROP POLICY IF EXISTS run_access ON runs_analysisrun;
ALTER TABLE runs_analysisrun NO FORCE ROW LEVEL SECURITY;
ALTER TABLE runs_analysisrun DISABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS client_access ON runs_client;
ALTER TABLE runs_client NO FORCE ROW LEVEL SECURITY;
ALTER TABLE runs_client DISABLE ROW LEVEL SECURITY;
"""


class Migration(migrations.Migration):

    dependencies = [("runs", "0001_initial")]

    operations = [migrations.RunSQL(ENABLE_SQL, reverse_sql=DISABLE_SQL)]
