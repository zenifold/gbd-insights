"""
One-command Supabase connectivity + posture check.

Verifies, against the configured Supabase project:
  * Storage  - ensures the private bucket exists and performs a full signed-URL
               round-trip (create signed upload -> PUT -> stat -> signed download
               -> GET -> delete).
  * Database - connects, reports the role, and warns if that role would BYPASS
               Row Level Security (i.e. is superuser / bypassrls), which would
               disable our defense-in-depth.

Run after putting SUPABASE_URL, SUPABASE_SERVICE_KEY, STORAGE_BUCKET and
DATABASE_URL in the environment:  python manage.py check_supabase
"""
from __future__ import annotations

import uuid

import requests
from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = "Verify connectivity and security posture against the configured Supabase project."

    def handle(self, *args, **options):
        ok = True
        ok &= self._check_storage()
        ok &= self._check_database()
        if ok:
            self.stdout.write(self.style.SUCCESS("\nAll Supabase checks passed."))
        else:
            self.stdout.write(self.style.ERROR("\nSome Supabase checks FAILED (see above)."))

    # ------------------------------------------------------------------
    def _check_storage(self) -> bool:
        self.stdout.write(self.style.MIGRATE_HEADING("Storage"))
        if settings.STORAGE_BACKEND != "supabase":
            self.stdout.write(f"  STORAGE_BACKEND={settings.STORAGE_BACKEND!r} (set to 'supabase' for cloud).")
        if not settings.SUPABASE_URL or not settings.SUPABASE_SERVICE_KEY:
            self.stdout.write(self.style.ERROR("  SUPABASE_URL / SUPABASE_SERVICE_KEY are not set."))
            return False

        from runs.storage.supabase import SupabaseStorage

        try:
            store = SupabaseStorage()
            state = store.ensure_bucket(public=False)
            self.stdout.write(f"  bucket '{settings.STORAGE_BUCKET}': {state}")

            test_path = f"_healthcheck/{uuid.uuid4()}.txt"
            payload = b"gbd-insights storage healthcheck"

            signed = store.create_signed_upload(test_path, content_type="text/plain")
            put = requests.put(signed.url, headers=signed.headers, data=payload, timeout=30)
            put.raise_for_status()
            self.stdout.write("  signed upload  -> OK")

            stat = store.stat(test_path)
            assert stat.exists and stat.size == len(payload), f"stat mismatch: {stat}"
            self.stdout.write(f"  stat           -> OK ({stat.size} bytes)")

            dl_url = store.create_signed_download(test_path, filename="hc.txt")
            got = requests.get(dl_url, timeout=30)
            got.raise_for_status()
            assert got.content == payload, "downloaded bytes differ"
            self.stdout.write("  signed download-> OK")

            store.delete(test_path)
            self.stdout.write("  cleanup        -> OK")
            self.stdout.write(self.style.SUCCESS("  Storage round-trip succeeded."))
            return True
        except Exception as exc:  # noqa: BLE001
            self.stdout.write(self.style.ERROR(f"  Storage check FAILED: {exc!r}"))
            return False

    # ------------------------------------------------------------------
    def _check_database(self) -> bool:
        self.stdout.write(self.style.MIGRATE_HEADING("Database"))
        try:
            with connection.cursor() as cur:
                cur.execute(
                    "SELECT current_user, "
                    "(SELECT rolsuper FROM pg_roles WHERE rolname = current_user), "
                    "(SELECT rolbypassrls FROM pg_roles WHERE rolname = current_user)"
                )
                user, is_super, bypass_rls = cur.fetchone()
            self.stdout.write(f"  connected as role: {user}")

            healthy = True
            if is_super or bypass_rls:
                self.stdout.write(self.style.WARNING(
                    "  WARNING: this role is superuser / BYPASSRLS - Row Level Security is "
                    "NOT enforced. Connect as a dedicated NOSUPERUSER NOBYPASSRLS role "
                    "(see db/supabase_setup.sql) to keep RLS as defense-in-depth."
                ))
                healthy = False
            else:
                self.stdout.write(self.style.SUCCESS("  role is non-superuser, non-bypassrls - RLS will be enforced."))

            # Confirm tables exist (migrations applied).
            with connection.cursor() as cur:
                cur.execute("SELECT to_regclass('public.runs_analysisrun')")
                exists = cur.fetchone()[0]
            if exists:
                self.stdout.write("  schema: runs_analysisrun present (migrations applied).")
            else:
                self.stdout.write(self.style.WARNING("  schema: tables missing - run `python manage.py migrate`."))
                healthy = False
            return healthy
        except Exception as exc:  # noqa: BLE001
            self.stdout.write(self.style.ERROR(f"  Database check FAILED: {exc!r}"))
            return False
