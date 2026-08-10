# syntax=docker/dockerfile:1
# ---------------------------------------------------------------------------
# S3K CRM backend — stateless FastAPI container.
#
# Multi-stage build with uv: dependencies resolve from uv.lock only, so image
# builds are reproducible and cache well. Portable to Railway and Kubernetes —
# no host paths, no baked secrets, config comes entirely from the environment.
# ---------------------------------------------------------------------------

FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Install dependencies first (cached until the lockfile changes).
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project --no-dev

COPY . /app

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev


FROM python:3.13-slim-bookworm AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH"

# Run as an unprivileged user.
RUN groupadd --system --gid 1001 app \
    && useradd --system --uid 1001 --gid app --no-create-home app

WORKDIR /app

COPY --from=builder --chown=app:app /app /app

USER app

EXPOSE 8000

# No secrets and no defaults for DATABASE_URL / REDIS_URL: the container must
# be given them by the orchestrator or it will fail fast at startup.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
