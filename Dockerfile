# Single image used by BOTH the Render web service and the worker service —
# they differ only by start command (see render.yaml).
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

# Install runtime dependencies first (better layer caching). --no-dev keeps test/
# browser tooling out of the image.
COPY pyproject.toml ./
RUN uv sync --no-dev --no-install-project

# Use the venv directly at runtime so we never re-sync (which would pull dev deps).
ENV PATH="/app/.venv/bin:$PATH"

# App code.
COPY . .

# Build Tailwind/DaisyUI CSS and collect static assets at build time.
RUN python manage.py tailwind build && \
    python manage.py collectstatic --noinput

EXPOSE 8000

# Default to the web process (binds Render's $PORT; falls back to 8000 locally).
# render.yaml overrides the command for the worker via dockerCommand.
CMD ["sh", "-c", "gunicorn config.wsgi --bind 0.0.0.0:${PORT:-8000} --workers ${WEB_CONCURRENCY:-3}"]
