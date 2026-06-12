# GBD Foodservice Insights — V1 internal tool

An internal web app that wraps Greener by Default's Python food-procurement
analysis pipeline. An analyst uploads a procurement spreadsheet, a background
worker runs the analysis, and the analyst downloads a PDF report.

Client flow: **upload → status → download**, plus a **GBD admin dashboard**
([`/dashboard`](runs/views.py)) showing every run across all clients with full
metadata and re-download of past outputs/inputs. Django + HTMX, Supabase
(Postgres + Storage), deployed on Render.

> **Status:** working end-to-end. The analysis is a real deterministic ETL
> ([`pipeline/`](pipeline/)); only the **emission factors** are placeholders
> pending GBD's validated values ([`pipeline/data/factors.json`](pipeline/data/factors.json)).

## Architecture

```
Browser (session login) ─1. create run──▶ Django web ──mint signed URL──▶
        └──2. PUT file directly──▶ Supabase Storage (private bucket)
        └──3. finalize──▶ Django marks run QUEUED
                                          │ Postgres queue (the runs table)
Worker (same image) ──claim (FOR UPDATE SKIP LOCKED)──▶ download ▶ validate ▶
        run pipeline ▶ upload artifact ▶ mark DONE/FAILED
```

* **Queue:** the `runs_analysisrun` table *is* the queue; the worker claims the
  oldest `QUEUED` row with `FOR UPDATE SKIP LOCKED`. No Celery/Redis.
* **Uploads** go **directly to object storage** via a short-lived signed URL —
  file bytes never pass through the web process (handles >100 MB cleanly).
* **Storage is pluggable** ([`runs/storage/`](runs/storage/)): a `local`
  filesystem adapter for dev (emulates the signed-URL flow) and a `supabase`
  adapter for production. Same browser flow either way.

## Security (top priority)

* **Session login + multi-tenancy** ([`django.contrib.auth`], [`runs/middleware.py`](runs/middleware.py),
  [`runs/scoping.py`](runs/scoping.py)). Each user has a [`Profile`](runs/models.py)
  linking them to a client (institution); GBD staff (`is_staff`) see everything.
  Every run view filters to the user's client (**primary** isolation), and the
  request's RLS scope is set from the user (**defense-in-depth**).
* **Row Level Security** is enabled and `FORCE`d on both tables
  ([`runs/migrations/0002_rls_policies.py`](runs/migrations/0002_rls_policies.py)).
  When connected as a **non-superuser** role, a per-request `SET LOCAL` GUC scopes
  visibility (service scope for staff, single-client for client users); with no
  scope the database returns nothing (deny by default).
* **Signed URLs** for both upload and download; the artifact bucket is private.
* **Secrets** are env-only; see [`.env.example`](.env.example). Never commit `.env`.
* **CSV/formula injection** — every CSV export is built from untrusted product/
  vendor text, so cells beginning with `= + - @` or control chars are prefixed
  with `'` ([`pipeline/report.py`](pipeline/report.py)) so spreadsheet apps can't
  execute them on open.
* **Malicious uploads** — `.xlsx` files that decompress beyond a limit are
  rejected (zip-bomb guard), and the local upload endpoint enforces a hard byte
  cap mid-stream ([`runs/validation.py`](runs/validation.py),
  [`runs/storage/local.py`](runs/storage/local.py)).
* **Insecure-default guard** — a deploy check ([`runs/checks.py`](runs/checks.py))
  fails the build if `DJANGO_SECRET_KEY` or `BASIC_AUTH_PASS` are left at their
  defaults when `DEBUG=False`; it runs in Render's `preDeployCommand` so a
  misconfigured deploy is blocked before serving traffic.

> **Connection note:** in production use a Supabase **session-mode** connection
> (port 5432 / direct), *not* the transaction pooler (6543) — the pooler would
> scramble the per-request `SET LOCAL` GUCs that RLS relies on.

## Local development

Prerequisites: [uv](https://docs.astral.sh/uv/), Docker.

```bash
uv sync                                   # install deps
cp .env.example .env                      # defaults work as-is for local dev
docker compose up -d                      # local Postgres (creates the gbd_app role)
uv run python manage.py migrate
uv run python manage.py createsuperuser   # the GBD admin (sees all clients)
uv run python manage.py create_client_account \
    --name "Acme University" --username acme --password 's3cret'   # a client account
uv run python manage.py tailwind build    # build DaisyUI CSS (downloads CLI once)

# Two terminals:
uv run python manage.py runserver         # web  → http://localhost:8000
uv run python manage.py run_worker        # worker
```

Open http://localhost:8000 and sign in. A **client** account (e.g. `acme`) uploads
[`sample_data/sample.csv`](sample_data/sample.csv) for its own org and sees only
its own runs; the **GBD admin** sees every client's runs and can manage clients +
accounts at `/django-admin/`.

## Data format (what to upload)

The upload page has a built-in **"How should my file be formatted?"** guide and a
**Download CSV template** button ([`/template.csv`](runs/views.py)). In short: one
row per line item, headers in row 1. **`product`** is required; provide **`spend`**
(USD) and/or **`quantity`** + **`unit`**. `vendor` and `date` are optional (a date
unlocks the by-period breakdown). Column names are flexible — synonyms like
`item`/`description`, `amount`/`cost`, `qty`, `supplier` are auto-detected
([`pipeline/ingest.py`](pipeline/ingest.py)), and the worker validates against the
same mapping, rejecting bad files with specific messages
([`runs/validation.py`](runs/validation.py)).

## Tests

```bash
uv run pytest                            # 57 unit/integration tests
uv run python scripts/shot_selfserve.py  # optional: headless self-serve UI check
```

Covers validation edge cases, the queue claim + reaper, the worker
happy/crash/validation paths, the two-step upload views, status-page metrics,
**multi-tenant isolation** (a client can't see or open another client's runs;
uploads auto-scope; admin views are staff-only), **RLS enforcement**, and pipeline
reproducibility. Requires the local Postgres running; the browser checks also need
the dev server + worker up (`uv run playwright install chromium` once).

## Deployment (Render)

[`render.yaml`](render.yaml) deploys **one free web service**. Uploads are
processed **inline in the web request** (`PROCESS_INLINE=true`), so no paid
background worker is needed — ideal for demos. For higher throughput, add a
second `type: worker` service (`dockerCommand: python manage.py run_worker`) on a
paid plan and set `PROCESS_INLINE=false`; both are built from the same
[`Dockerfile`](Dockerfile).

Set these env vars (see `.env.example`): `DJANGO_SECRET_KEY`,
`DJANGO_ALLOWED_HOSTS`, `PUBLIC_BASE_URL`, `DJANGO_CSRF_TRUSTED_ORIGINS`,
`DATABASE_URL` (Supabase session mode), `STORAGE_BACKEND=supabase`,
`SUPABASE_URL`, `SUPABASE_SERVICE_KEY`. Create the GBD admin after first deploy
with `createsuperuser` (Render Shell).

### Supabase setup (cloud)
1. **App DB role** — run [`db/supabase_setup.sql`](db/supabase_setup.sql) in the
   Supabase SQL editor to create the non-superuser `gbd_app` role (so RLS is
   enforced; the built-in `postgres` user bypasses it).
2. **Env** — set `STORAGE_BACKEND=supabase`, `SUPABASE_URL`,
   `SUPABASE_SERVICE_KEY` (the `sb_secret_…`/service-role key — never the
   publishable/anon key), `STORAGE_BUCKET=gbd-procurement`, and `DATABASE_URL`
   using the **session-mode** connection (port 5432) as `gbd_app`.
3. **Migrate** — `python manage.py migrate` (tables are created and owned by
   `gbd_app`, keeping them off the public Data API and under FORCE RLS).
4. **Verify** — `python manage.py check_supabase` ensures the private bucket
   exists, runs a full signed-URL storage round-trip, and confirms the DB role
   does not bypass RLS.
5. **CORS** — if the browser's direct PUT is blocked, add the web app origin to
   the Storage CORS allow-list in the Supabase dashboard.

### Operations / alerts (handover)
* Alert on **worker service down/restart** (Render service health) and on
  **storage usage thresholds** (Supabase dashboard).
* A run stuck in `RUNNING` past `WORKER_STALE_SECONDS` is auto-requeued by the
  worker's startup/periodic reaper; after `WORKER_MAX_ATTEMPTS` it is failed with
  a human-readable message.

## Data pipeline (ETL)

A real, deterministic ETL lives in [`pipeline/`](pipeline/) behind
`run_pipeline(input_path, workdir) -> PipelineResult`
([`pipeline/interface.py`](pipeline/interface.py)). Stages:

1. **ingest** ([`ingest.py`](pipeline/ingest.py)) — read CSV/XLSX, map header
   synonyms (`item`→product, `amount`→spend, …) to canonical columns.
2. **clean** ([`clean.py`](pipeline/clean.py)) — coerce money/quantity, normalize
   units, derive mass in kg, parse a reporting period, drop/flag bad rows, emit a
   data-quality report.
3. **categorize** ([`categorize.py`](pipeline/categorize.py)) — deterministic
   keyword rules map each item to exactly one GBD category (no LLM → reproducible).
4. **emissions** ([`emissions.py`](pipeline/emissions.py)) — mass-based factor
   (`mass × kgCO2e/kg`) where mass is known, else spend-based fallback.
5. **aggregate** ([`aggregate.py`](pipeline/aggregate.py)) — by category & period,
   top contributors, headline totals.
6. **report** ([`report.py`](pipeline/report.py)) — write the output set and a
   deterministic ZIP bundle.

**The science is data-driven** — edit [`pipeline/data/`](pipeline/data/):
`categories.json` (taxonomy/keywords), `factors.json` (emission factors),
`units.json` (unit→kg). The factor table is **placeholder** (Poore & Nemecek 2018
midpoints + rough spend-based fallbacks) and must be replaced by GBD's validated
factors and the additional impact metrics.

**Output bundle** (one downloadable ZIP, usable in GBD workflows):
`report.pdf`, `line_items_categorized.csv` (auditable per-row ETL output),
`aggregates_by_category.csv`, `aggregates_by_period.csv`, `top_products.csv`,
`summary.json`, `data_quality.json`, and `manifest.json` (input SHA-256 +
per-output SHA-256 + factor/pipeline versions).

**Reproducibility:** same input + config → byte-identical data files *and* a
byte-identical bundle (reportlab invariant mode + fixed ZIP timestamps). Verified
by `pipeline/tests/test_pipeline.py::test_outputs_are_reproducible`; the manifest
hashes let GBD audit/re-verify any report.
