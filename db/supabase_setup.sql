-- Harden the Supabase database so Row Level Security is actually ENFORCED.
--
-- Run ONCE in the Supabase SQL editor (it runs as a privileged role). Safe to run
-- after migrations have already been applied as `postgres` — it also transfers
-- ownership of the app tables to gbd_app so future migrations keep working.
--
-- STEPS:
--   1. Replace 'CHANGE_ME_STRONG_PASSWORD' below with a strong password.
--   2. Run the whole script.
--   3. Use this connection string (SESSION pooler, port 5432) in Render's
--      DATABASE_URL env var:
--        postgresql://gbd_app.<project-ref>:<password>@<pooler-host>:5432/postgres?sslmode=require
--      For this project:
--        host = aws-1-us-west-2.pooler.supabase.com   ref = llicruaiqnytjxwyatad
--   4. Verify:  DATABASE_URL=... STORAGE_BACKEND=supabase SUPABASE_URL=... \
--               SUPABASE_SERVICE_KEY=... python manage.py check_supabase

-- 1. The non-superuser application role (postgres bypasses RLS; gbd_app does not).
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'gbd_app') THEN
        CREATE ROLE gbd_app LOGIN PASSWORD 'CHANGE_ME_STRONG_PASSWORD'
            NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE;
    ELSE
        ALTER ROLE gbd_app WITH LOGIN PASSWORD 'CHANGE_ME_STRONG_PASSWORD'
            NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE;
    END IF;
END
$$;

-- 2. Let the current admin reassign ownership to gbd_app, and let gbd_app use the schema.
GRANT gbd_app TO CURRENT_USER;
GRANT CONNECT ON DATABASE postgres TO gbd_app;
GRANT USAGE, CREATE ON SCHEMA public TO gbd_app;

-- 3. Transfer ownership of every app table/sequence in `public` to gbd_app so it
--    owns the schema (future migrations run as gbd_app) and FORCE RLS applies to it.
DO $$
DECLARE r record;
BEGIN
    FOR r IN SELECT tablename FROM pg_tables WHERE schemaname = 'public' LOOP
        EXECUTE format('ALTER TABLE public.%I OWNER TO gbd_app', r.tablename);
    END LOOP;
    FOR r IN SELECT sequencename FROM pg_sequences WHERE schemaname = 'public' LOOP
        EXECUTE format('ALTER SEQUENCE public.%I OWNER TO gbd_app', r.sequencename);
    END LOOP;
END
$$;

-- 4. Defense-in-depth: don't expose gbd_app's tables to the public Data API roles.
ALTER DEFAULT PRIVILEGES FOR ROLE gbd_app IN SCHEMA public
    REVOKE ALL ON TABLES FROM anon, authenticated;
