"""
One-off: create the non-superuser `gbd_app` role on Supabase, transfer ownership
of the app's public tables/sequences to it, and verify RLS is now enforced.

Admin (postgres) password is read from env ADMIN_PW so it isn't hard-coded.
The generated gbd_app password is written into .env's PRODUCTION block — never
printed to the terminal.

    ADMIN_PW='...' uv run python scripts/setup_gbd_role.py
"""
import os
import re
import secrets
from pathlib import Path

import psycopg

REF = "llicruaiqnytjxwyatad"
HOST = "aws-1-us-west-2.pooler.supabase.com"
ADMIN_PW = os.environ["ADMIN_PW"]
APP_PW = secrets.token_hex(24)  # url-safe (hex), no encoding needed

# --- 1. As postgres: create role, grants, transfer ownership ---------------
admin = psycopg.connect(
    host=HOST, port=5432, user=f"postgres.{REF}", password=ADMIN_PW,
    dbname="postgres", sslmode="require", connect_timeout=20, autocommit=True,
)
c = admin.cursor()
# APP_PW is hex (token_hex) so inlining is injection-safe; CREATE/ALTER ROLE
# don't accept bound parameters for the password.
assert all(ch in "0123456789abcdef" for ch in APP_PW)
c.execute("SELECT 1 FROM pg_roles WHERE rolname='gbd_app'")
if c.fetchone():
    # Only reset password/login; changing SUPERUSER/BYPASSRLS flags needs superuser.
    c.execute(f"ALTER ROLE gbd_app WITH LOGIN PASSWORD '{APP_PW}'")
    print("role: reset gbd_app password")
else:
    c.execute(
        f"CREATE ROLE gbd_app WITH LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB "
        f"NOCREATEROLE PASSWORD '{APP_PW}'"
    )
    print("role: created gbd_app")

# Grant gbd_app least-privilege DML on the app schema. Tables stay owned by
# postgres (migrations run as the admin); gbd_app is the runtime role, and because
# it is non-bypassrls the FORCE RLS policies are enforced for it.
c.execute("GRANT CONNECT ON DATABASE postgres TO gbd_app")
c.execute("GRANT USAGE ON SCHEMA public TO gbd_app")
c.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO gbd_app")
c.execute("GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO gbd_app")
# Future tables/sequences created by the admin are usable by gbd_app too.
c.execute("ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public "
          "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO gbd_app")
c.execute("ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public "
          "GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO gbd_app")
print("grants: DML on public granted to gbd_app")
admin.close()

# --- 2. As gbd_app: verify posture + RLS enforcement -----------------------
app = psycopg.connect(
    host=HOST, port=5432, user=f"gbd_app.{REF}", password=APP_PW,
    dbname="postgres", sslmode="require", connect_timeout=20,
)
ac = app.cursor()
ac.execute("SELECT current_user,(SELECT rolsuper FROM pg_roles WHERE rolname=current_user),(SELECT rolbypassrls FROM pg_roles WHERE rolname=current_user)")
user, is_super, bypass = ac.fetchone()
print(f"gbd_app posture: user={user} super={is_super} bypassrls={bypass}")

# deny-by-default: no scope -> sees nothing
ac.execute("SELECT count(*) FROM runs_client")
no_scope = ac.fetchone()[0]
app.rollback()
# service scope -> sees rows
ac.execute("SELECT set_config('app.scope','service',true)")
ac.execute("SELECT count(*) FROM runs_client")
with_scope = ac.fetchone()[0]
app.commit()
app.close()
print(f"RLS check: without scope={no_scope}  with service scope={with_scope}")
rls_ok = (not is_super) and (not bypass) and no_scope == 0 and with_scope >= 1
print("RLS ENFORCED: OK" if rls_ok else "RLS NOT enforced: FAILED")

# --- 3. Write the gbd_app connection into .env PRODUCTION block -------------
env_path = Path(".env")
url = f"postgresql://gbd_app.{REF}:{APP_PW}@{HOST}:5432/postgres?sslmode=require"
text = env_path.read_text(encoding="utf-8")
text = re.sub(
    r"^# DATABASE_URL=postgresql://postgres\.llicruaiqnytjxwyatad.*$",
    f"# DATABASE_URL={url}",
    text, flags=re.MULTILINE,
)
text = re.sub(
    r"^# \(More secure:.*$",
    "# (gbd_app role created -- RLS enforced. Set the line above in Render.)",
    text, flags=re.MULTILINE,
)
env_path.write_text(text, encoding="utf-8")
print(".env: PRODUCTION DATABASE_URL updated to gbd_app (secret not printed)")
