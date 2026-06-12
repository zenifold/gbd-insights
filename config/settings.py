"""
Django settings for the GBD Foodservice Insights tool (V1).

Configuration is 12-factor / environment-driven. For local development the
defaults below + a `.env` file are enough to run the whole stack against a
local Postgres and the filesystem storage backend (no Supabase account needed).
In production, point DATABASE_URL at Supabase and set STORAGE_BACKEND=supabase.
"""
from pathlib import Path

import dj_database_url
import environ

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env()
# Read a local .env if present (never commit it).
environ.Env.read_env(BASE_DIR / ".env")

# --------------------------------------------------------------------------
# Core
# --------------------------------------------------------------------------
SECRET_KEY = env("DJANGO_SECRET_KEY", default="dev-insecure-change-me")
DEBUG = env.bool("DJANGO_DEBUG", default=True)
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])
CSRF_TRUSTED_ORIGINS = env.list("DJANGO_CSRF_TRUSTED_ORIGINS", default=[])

# Public base URL used to build absolute links (e.g. local signed-storage URLs).
PUBLIC_BASE_URL = env("PUBLIC_BASE_URL", default="http://localhost:8000")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django_tailwind_cli",
    "runs",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    # Require login for app pages (clients + GBD staff).
    "runs.middleware.LoginRequiredMiddleware",
    # Establishes the per-request Postgres RLS context from the logged-in user.
    "runs.middleware.RLSContextMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# Authentication
LOGIN_URL = "/login"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/login"
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

WSGI_APPLICATION = "config.wsgi.application"

# --------------------------------------------------------------------------
# Database
# --------------------------------------------------------------------------
# Local dev default connects as the non-superuser `gbd_app` role so that RLS
# policies are actually enforced (a superuser would silently bypass them).
DATABASES = {
    "default": dj_database_url.parse(
        env(
            "DATABASE_URL",
            default="postgres://gbd_app:gbd_app@localhost:5432/gbd",
        ),
        conn_max_age=env.int("DB_CONN_MAX_AGE", default=0),
    )
}
# IMPORTANT: use a SESSION-mode connection (Supabase port 5432 / direct), not the
# transaction pooler (6543), so per-request `SET LOCAL` GUCs for RLS behave.

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --------------------------------------------------------------------------
# Static files (WhiteNoise + Tailwind/DaisyUI standalone CLI)
# --------------------------------------------------------------------------
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "assets"]
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}
TAILWIND_CLI_USE_DAISY_UI = True

# --------------------------------------------------------------------------
# Auth — paths reachable without logging in (health, login, the local
# signed-storage endpoints which carry their own HMAC token).
# --------------------------------------------------------------------------
LOGIN_EXEMPT_PREFIXES = ["/healthz", "/login", "/logout", "/_storage/", "/static/"]

# --------------------------------------------------------------------------
# Storage backend (uploads + report artifacts)
# --------------------------------------------------------------------------
STORAGE_BACKEND = env("STORAGE_BACKEND", default="local")  # "local" | "supabase"
STORAGE_BUCKET = env("STORAGE_BUCKET", default="gbd-procurement")

# Local filesystem backend (dev): emulates the two-step signed-URL upload flow.
LOCAL_STORAGE_ROOT = Path(env("LOCAL_STORAGE_ROOT", default=str(BASE_DIR / "var" / "storage")))
STORAGE_SIGNING_KEY = env("STORAGE_SIGNING_KEY", default=SECRET_KEY)
STORAGE_SIGNED_URL_TTL = env.int("STORAGE_SIGNED_URL_TTL", default=3600)  # seconds

# Supabase backend (prod): server-side service key, private bucket.
SUPABASE_URL = env("SUPABASE_URL", default="")
SUPABASE_SERVICE_KEY = env("SUPABASE_SERVICE_KEY", default="")

# --------------------------------------------------------------------------
# Upload / pipeline limits
# --------------------------------------------------------------------------
MAX_UPLOAD_BYTES = env.int("MAX_UPLOAD_BYTES", default=100 * 1024 * 1024)  # 100 MB
ALLOWED_UPLOAD_EXTENSIONS = [".csv", ".xlsx"]
# Reject .xlsx whose decompressed size is implausibly large (zip/decompression bomb).
MAX_XLSX_UNCOMPRESSED_BYTES = env.int("MAX_XLSX_UNCOMPRESSED_BYTES", default=1024 * 1024 * 1024)
# Validation requires a detectable product column plus a spend or quantity column
# (see runs/validation.py, which reuses pipeline.ingest's synonym mapping).

# --------------------------------------------------------------------------
# Worker
# --------------------------------------------------------------------------
WORKER_POLL_INTERVAL = env.float("WORKER_POLL_INTERVAL", default=2.0)  # seconds
WORKER_STALE_SECONDS = env.int("WORKER_STALE_SECONDS", default=900)  # reaper threshold
WORKER_MAX_ATTEMPTS = env.int("WORKER_MAX_ATTEMPTS", default=3)

# --------------------------------------------------------------------------
# Security hardening (effective when DEBUG=False)
# --------------------------------------------------------------------------
if not DEBUG:
    SECURE_SSL_REDIRECT = env.bool("DJANGO_SECURE_SSL_REDIRECT", default=True)
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = env.int("DJANGO_HSTS_SECONDS", default=31536000)
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": env("DJANGO_LOG_LEVEL", default="INFO")},
}
