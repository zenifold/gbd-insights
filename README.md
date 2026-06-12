# GBD Foodservice Insights

An internal web app that turns a client's food‑procurement spreadsheet into a
carbon‑footprint analysis. A user uploads a purchasing file, a deterministic
Python ETL analyzes it, and the app shows an interactive report (and a
downloadable PDF/CSV/JSON bundle).

**Client flow:** `upload → live progress → interactive report + download`.
**GBD staff** also get a dashboard ([`/dashboard`](runs/views.py)) of every run
across all clients, with metadata and re‑download of past inputs/outputs.

Stack: **Django + HTMX**, **Tailwind/DaisyUI** (no Node — standalone CLI),
**Supabase** (Postgres + Storage), deployable on **Render**. Managed with
[`uv`](https://docs.astral.sh/uv/).

> **Status:** working end‑to‑end, 60 passing tests. The analysis is a real,
> reproducible ETL ([`pipeline/`](pipeline/)); only the **emission factors** are
> placeholders pending GBD's validated values
> ([`pipeline/data/factors.json`](pipeline/data/factors.json)).

---

## Contents
1. [Run it locally](#1-run-it-locally)
2. [What you can upload](#2-what-you-can-upload)
3. [The analysis (Python ETL)](#3-the-analysis-python-etl)
4. [Plug in your own Python](#4-plug-in-your-own-python)
5. [Put it online (domain + cloud DB)](#5-put-it-online-domain--cloud-db)
6. [Security](#6-security)
7. [Tests & operations](#7-tests--operations)

---

## 1. Run it locally

**Prerequisites:** [uv](https://docs.astral.sh/uv/) and Docker Desktop.

```bash
uv sync                                    # install Python deps into .venv
cp .env.example .env                       # defaults work as‑is for local dev
docker compose up -d                       # local Postgres (creates the gbd_app role)
uv run python manage.py migrate            # create tables + RLS policies
uv run python manage.py tailwind build     # build the CSS (downloads the CLI once)
uv run python manage.py createsuperuser    # your GBD admin login (sees all runs)
```

Then start the app. Locally the DB‑backed queue is drained by a **worker**, so
run two processes (two terminals):

```bash
uv run python manage.py runserver          # web  → http://localhost:8000
uv run python manage.py run_worker         # background analysis worker
```

> Prefer a single process? Set `PROCESS_INLINE=true` in `.env` and skip the
> worker — uploads are then analyzed inline in the web request. (Good for quick
> demos; the live progress bar won't stream stage‑by‑stage in this mode.)

Open <http://localhost:8000>, sign in as the admin, and upload a file —
[`sample_data/sample.csv`](sample_data/sample.csv) is a quick start. To onboard a
real client with its own self‑serve login (scoped to only their data):

```bash
uv run python manage.py create_client_account --name "Acme University" --username acme --password 's3cret'
```

**Editing styles:** the brand theme lives in [`styles/source.css`](styles/source.css).
After changing it, rebuild with `uv run python manage.py tailwind build --force`
(and `collectstatic` before deploying — see §5).

---

## 2. What you can upload

One row per line item, headers in row 1. Column names are flexible — synonyms are
auto‑detected ([`pipeline/ingest.py`](pipeline/ingest.py)).

| Column | Required? | Synonyms accepted | Notes |
|---|---|---|---|
| `product` | **Yes** | `item`, `description` | what was purchased |
| `spend` | one of spend / quantity | `amount`, `cost`, `price` | USD |
| `quantity` + `unit` | one of spend / quantity | `qty` | weight (`lb, oz, kg, g`) or volume (`gal, l, ml, qt`) → weight‑based estimate; other units (`case, each`) fall back to spend |
| `vendor` | optional | `supplier` | |
| `date` | optional | | unlocks the month‑by‑month breakdown |

The upload page has a built‑in format guide and a **Download CSV template**
button ([`/template.csv`](runs/views.py)). Bad files are rejected with specific,
human‑readable messages ([`runs/validation.py`](runs/validation.py)).

---

## 3. The analysis (Python ETL)

A real, deterministic ETL lives in [`pipeline/`](pipeline/) behind one entry
point — `run_pipeline(input_path, out_dir, *, on_progress=None) -> PipelineResult`
([`pipeline/interface.py`](pipeline/interface.py)). Stages:

1. **ingest** ([`ingest.py`](pipeline/ingest.py)) — read CSV/XLSX, map header
   synonyms to canonical columns.
2. **clean** ([`clean.py`](pipeline/clean.py)) — coerce money/quantity, normalize
   units, derive **mass in kg** (from weight *or* volume × density), parse a
   reporting period, drop/flag bad rows, emit a data‑quality report.
3. **categorize** ([`categorize.py`](pipeline/categorize.py)) — token‑aware
   keyword rules map each item to exactly one GBD category (no LLM →
   reproducible). Includes a **plant‑based alternatives** category so Beyond /
   Impossible / oat & almond milk are recognized, not mislabeled as meat/dairy.
4. **emissions** ([`emissions.py`](pipeline/emissions.py)) — best available
   method per item: **mass‑based** (`mass × kgCO₂e/kg`, high confidence) →
   **volume‑based** (via density, medium) → **spend‑based** fallback (low). The
   method + confidence is recorded per row.
5. **aggregate** ([`aggregate.py`](pipeline/aggregate.py)) — totals, by category &
   month, top contributors, carbon **intensity** (per $ and per kg of food), a
   **data‑quality score**, and real‑world **equivalencies** (cars, gasoline,
   trees, homes).
6. **report** ([`report.py`](pipeline/report.py)) — write the output set + a
   deterministic ZIP bundle.

**The science is data‑driven** — edit [`pipeline/data/`](pipeline/data/) with no
code changes:

| File | Controls |
|---|---|
| [`categories.json`](pipeline/data/categories.json) | the taxonomy: category order + keywords |
| [`factors.json`](pipeline/data/factors.json) | emission factors (`kgCO₂e/kg`, spend fallback) + source citation |
| [`units.json`](pipeline/data/units.json) | unit→kg, unit→liter, and per‑category densities |

> ⚠️ The factor table is a **placeholder** (Poore & Nemecek 2018 midpoints +
> rough spend‑based fallbacks). Replace it with GBD's validated factors — and add
> the additional impact metrics (land, water, animal lives, health) — before
> production use.

**Output bundle** (one ZIP): `report.pdf`, `line_items_categorized.csv`
(auditable per‑row output), `aggregates_by_category.csv`,
`aggregates_by_period.csv`, `top_products.csv`, `summary.json`,
`data_quality.json`, and `manifest.json` (input SHA‑256 + per‑output SHA‑256 +
factor/pipeline versions).

**Reproducible:** same input + config → byte‑identical bundle (verified in
[`pipeline/tests/test_pipeline.py`](pipeline/tests/test_pipeline.py)); the
manifest hashes let GBD audit/re‑verify any report.

---

## 4. Plug in your own Python

The web app and worker depend only on the **contract**, not the implementation:

```python
def run_pipeline(input_path: Path, out_dir: Path, *, on_progress=None) -> PipelineResult: ...
# PipelineResult(artifact_path: Path, summary: dict, warnings: list[str])
#   artifact_path -> a file to offer for download (e.g. a .zip or .pdf)
#   summary       -> dict shown in the in‑app report (the keys the UI reads are
#                    listed at the top of templates/partials/_report.html)
#   on_progress(percent:int, message:str)  -> optional; call it to drive the
#                    live progress bar (safe to ignore)
```

You have two ways to swap in GBD's own analysis code:

**A. Edit in place.** Keep the `pipeline/` package and the `run_pipeline`
signature; change the internals (or the data files in `pipeline/data/`).

**B. Point at your own module (no app edits).** Set one env var to a dotted path:

```bash
PIPELINE_CALLABLE=my_company.analysis.run   # default: pipeline.run_pipeline
```

`runs/processing.py` imports that callable and runs it for every job. If your
callable doesn't accept `on_progress`, it's simply called without it. Return a
`PipelineResult` (import it from `pipeline`, or return any object with the same
three attributes) and the rest of the app — queue, storage, status page,
download, audit — works unchanged.

---

## 5. Put it online (domain + cloud DB)

Production = **Supabase** (Postgres + private Storage bucket) + **Render** (runs
the same Docker image as web, and optionally a worker). End‑to‑end:

### Step 1 — Supabase (database + storage)
1. Create a project at [supabase.com](https://supabase.com). Note the project
   **URL** and the **service‑role key** (`sb_secret_…` — server‑side only; never
   the anon/publishable key).
2. **Storage:** create a **private** bucket named `gbd-procurement`.
3. **App DB role:** in the SQL editor, run
   [`db/supabase_setup.sql`](db/supabase_setup.sql) to create the non‑superuser
   `gbd_app` role. This matters for security — the built‑in `postgres` user
   *bypasses* Row‑Level Security; `gbd_app` does not, so tenant isolation is
   actually enforced.
4. **Connection string:** use the **session‑mode** pooler connection (port
   **5432**), *not* the transaction pooler (6543) — the pooler would scramble the
   per‑request `SET LOCAL` settings that RLS relies on. Format:
   `postgres://gbd_app:<password>@<host>:5432/postgres`.

### Step 2 — Deploy to Render
[`render.yaml`](render.yaml) defines a **free single web service** that processes
uploads inline (`PROCESS_INLINE=true`) — no paid worker needed for a demo.

1. Push this repo to GitHub, then in Render: **New → Blueprint** and pick the repo
   (it reads `render.yaml`). Or **New → Web Service** → Docker.
2. Set the environment variables Render marks as `sync: false`:

   | Var | Value |
   |---|---|
   | `DATABASE_URL` | the Supabase **session‑mode** URL from Step 1 |
   | `SUPABASE_URL` | your project URL |
   | `SUPABASE_SERVICE_KEY` | the `sb_secret_…` service‑role key |
   | `STORAGE_BACKEND` | `supabase` |
   | `STORAGE_BUCKET` | `gbd-procurement` |
   | `DJANGO_ALLOWED_HOSTS` | your domain(s), e.g. `insights.greenerbydefault.com` |
   | `PUBLIC_BASE_URL` | `https://insights.greenerbydefault.com` |
   | `DJANGO_CSRF_TRUSTED_ORIGINS` | `https://insights.greenerbydefault.com` |

   `DJANGO_SECRET_KEY` is auto‑generated and `DJANGO_DEBUG=False` by the blueprint.
3. **Apply migrations** once (Render **Shell**): `python manage.py migrate`.
4. **Verify Supabase wiring:** `python manage.py check_supabase` — confirms the
   private bucket exists, runs a full signed‑URL storage round‑trip, and asserts
   the DB role does **not** bypass RLS.
5. **Create the GBD admin:** `python manage.py createsuperuser` (Render Shell).

### Step 3 — Custom domain
In Render → your service → **Settings → Custom Domains**, add
`insights.greenerbydefault.com` and create the shown CNAME at your DNS provider.
Render provisions HTTPS automatically. Make sure the domain is also in
`DJANGO_ALLOWED_HOSTS`, `PUBLIC_BASE_URL`, and `DJANGO_CSRF_TRUSTED_ORIGINS`
(re‑deploy after changing env vars).

> If the browser's direct file upload is blocked, add your web origin to the
> Storage **CORS** allow‑list in the Supabase dashboard.

### Scaling beyond a demo
Add a second Render service of `type: worker` with
`dockerCommand: python manage.py run_worker`, set `PROCESS_INLINE=false`, and move
both services to a paid plan (the worker can't run on the free tier). Both are
built from the same [`Dockerfile`](Dockerfile).

---

## 6. Security

Data security is the top priority of this build.

* **Multi‑tenant isolation, two layers.** Every run view filters to the user's
  client (**primary**, [`runs/scoping.py`](runs/scoping.py)), *and* Postgres
  **Row‑Level Security** is enabled + `FORCE`d on the tables
  ([`0002_rls_policies.py`](runs/migrations/0002_rls_policies.py)). Connected as
  the non‑superuser `gbd_app` role, a per‑request `SET LOCAL` scopes visibility;
  with no scope the DB returns nothing (**deny by default**).
* **Direct‑to‑storage uploads** via short‑lived **signed URLs** — file bytes
  never pass through the web process; the artifact bucket is private.
* **Secrets are env‑only** ([`.env.example`](.env.example)); never commit `.env`.
  A deploy check ([`runs/checks.py`](runs/checks.py)) blocks the build if the
  secret key is left at its default when `DEBUG=False`.
* **CSV/formula‑injection safe** — untrusted product/vendor text starting with
  `= + - @` is prefixed with `'` so spreadsheets can't execute it
  ([`pipeline/report.py`](pipeline/report.py)).
* **Malicious uploads** — zip‑bomb guard on `.xlsx`, hard byte cap enforced
  mid‑stream ([`runs/validation.py`](runs/validation.py)).

---

## 7. Tests & operations

```bash
uv run pytest                              # 60 unit/integration tests
uv run python scripts/shot_selfserve.py    # optional headless UI check
```

Coverage: validation edge cases, the queue claim + crash‑reaper, worker
happy/crash/validation paths, the two‑step upload, status‑page metrics, **the ETL
(categorization, emissions, reproducibility)**, **multi‑tenant isolation**, and
**RLS enforcement**. The DB tests need the local Postgres up; browser checks need
the dev server + worker (`uv run playwright install chromium` once).

**Operations:** alert on worker down/restart (Render health) and Storage usage
(Supabase). A run stuck in `RUNNING` past `WORKER_STALE_SECONDS` is auto‑requeued
by the worker's reaper; after `WORKER_MAX_ATTEMPTS` it's failed with a friendly
message. After any schema change, re‑run `python manage.py migrate`.
