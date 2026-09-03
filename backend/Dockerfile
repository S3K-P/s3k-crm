# syntax=docker/dockerfile:1
# ---------------------------------------------------------------------------
# S3K CRM backend — stateless FastAPI container.
#
# Multi-stage build with uv: dependencies resolve from uv.lock only, so image
# builds are reproducible. Portable to Railway and Kubernetes — no host paths,
# no baked secrets, config comes entirely from the environment.
#
# Deliberately free of BuildKit `--mount` flags. Railway's builder rejects a
# `--mount=type=cache` that carries no `id=`, which is what made every build
# here fail to parse before the first layer ran. Ordinary COPY + RUN needs no
# BuildKit extension at all, so the same file builds on Railway, on plain
# Docker and in CI, and Docker's own layer cache still skips the dependency
# install whenever uv.lock is unchanged — which is what actually makes
# rebuilds fast.
# ---------------------------------------------------------------------------

FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Dependency layer, kept separate from the source so it is rebuilt only when
# the lockfile moves. `--no-install-project` means the application itself is
# not built here, so its README is not needed yet.
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-install-project --no-dev

COPY . /app

RUN uv sync --locked --no-dev


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

# Documentation only. The port actually bound is $PORT, which the platform
# assigns at run time; see scripts/start.sh.
EXPOSE 8000

# No secrets and no defaults for DATABASE_URL / REDIS_URL: the container must
# be given them by the orchestrator or it will fail fast at startup.
#
# Invoked through `sh` rather than as an executable, so the image does not
# depend on the script's mode bit surviving a checkout on a filesystem that
# does not carry one.
CMD ["sh", "/app/scripts/start.sh"]
