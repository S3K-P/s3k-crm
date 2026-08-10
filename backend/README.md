# S3K CRM Backend

Python 3.13 + FastAPI modular monolith (ADR-001, ADR-002), managed with
[uv](https://docs.astral.sh/uv/). One deployable application containing the
Shared Platform layer and the S3K CRM product.

> **Status: Phase 0 scaffold.** Application factory, configuration, database
> and Redis wiring, health probes, Alembic and the module tree exist. There is
> no authentication, no tenant context, no RLS and no CRM business logic yet —
> those are later Phase 0 and Phase 1 tasks.

## Stack

| Concern | Choice | ADR |
|---------|--------|-----|
| Language | Python 3.13 | ADR-002 |
| Framework | FastAPI | ADR-002 |
| Database | PostgreSQL 18 | ADR-005 |
| ORM | SQLAlchemy 2.0 async + asyncpg | ADR-006 |
| Migrations | Alembic (async) | ADR-006 |
| Validation / config | Pydantic v2 + pydantic-settings | ADR-002 |
| Cache / queue transport | Redis 7 | ADR-013 |
| Logging | structlog (JSON) | ADR-018 |
| Lint / format | Ruff | — |
| Types | mypy strict | — |
| Tests | pytest + pytest-asyncio | — |

## Getting started

Start infrastructure from the repository root first:

```bash
cp .env.example .env      # set POSTGRES_PASSWORD
docker compose up -d
```

Then the backend:

```bash
cd backend
cp .env.example .env      # DATABASE_URL must match the compose credentials
uv sync
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

The application is also runnable as a container:
`docker compose --profile backend up -d --build`.

## Health endpoints

| Endpoint | Meaning |
|----------|---------|
| `GET /health` | Liveness. 200 whenever the process runs; touches no dependency. |
| `GET /health/ready` | Readiness. 200 only when PostgreSQL **and** Redis answer, else 503. |

```bash
curl http://localhost:8000/health
curl -i http://localhost:8000/health/ready
```

```json
{ "service": "s3k-crm-backend", "status": "healthy", "environment": "development" }
```

Readiness reports each dependency as `up` or `down`. Failure detail is written
to the structured log only — responses never expose connection strings,
hostnames or driver errors.

## Quality gates

```bash
uv run ruff format --check .
uv run ruff check .
uv run mypy app
uv run pytest
```

All four must pass before a PR merges (Definition of Done, master plan §2.4).

## Migrations

```bash
uv run alembic current
uv run alembic revision --autogenerate -m "message"
uv run alembic upgrade head
```

`migrations/env.py` pulls the database URL from `app.core.config` and targets
`app.core.metadata.target_metadata` — the same metadata the runtime uses — so
migrations cannot drift from the application. See
[migrations/README.md](./migrations/README.md).

`versions/` is empty on purpose: no tables are defined yet.

## Configuration

Typed and validated by `pydantic-settings` in `app/core/config.py`. Values come
from the environment or the git-ignored `backend/.env`; see
[.env.example](./.env.example) for the full list.

`DATABASE_URL` and `REDIS_URL` are **required and have no default** — a
misconfigured process exits immediately with a readable message rather than
falling back to something insecure. `ENVIRONMENT=production` additionally
rejects `DEBUG=true` and `DB_ECHO=true`, and disables `/docs` and
`/openapi.json`.

## Layout

```
backend/
├── pyproject.toml            deps, Ruff, mypy, pytest configuration
├── uv.lock                   resolved dependency lockfile
├── alembic.ini               no credentials — env.py supplies the URL
├── Dockerfile                multi-stage, non-root, stateless
├── .env.example
├── app/
│   ├── main.py               ASGI entrypoint; validates config, fails fast
│   ├── application.py        application factory + lifespan
│   ├── api/
│   │   ├── router.py         root_router (health) + versioned api_router
│   │   └── health.py         liveness and readiness probes
│   ├── core/
│   │   ├── config.py         typed settings
│   │   ├── database.py       async engine, session factory, DbSession dep
│   │   ├── metadata.py       single metadata target for Alembic
│   │   ├── redis.py          async client + lifecycle
│   │   ├── logging.py        structlog configuration
│   │   └── exceptions.py     error hierarchy + structured handlers
│   ├── platform/             Shared Platform (ADR-003)
│   │   ├── auth/  organizations/  authorization/
│   │   └── documents/  audit/  notifications/
│   └── products/
│       └── crm/              S3K CRM (ADR-004)
│           ├── accounts/  contacts/  leads/  opportunities/
│           └── activities/  tasks/  notes/  dashboard/
├── migrations/               Alembic (async), versions/ empty by design
└── tests/
    ├── unit/
    └── integration/
```

Every business module carries the same seven files — `router`, `service`,
`repository`, `schemas`, `models`, `policies`, `events` — currently documented
placeholders.

## Module boundaries

Platform must never import a product; products consume Platform through
service interfaces only; no CRM entity lives in the Platform layer; one
database, one migration history; no microservices. The rules and their
enforcement are specified in
[ARCHITECTURE-BOUNDARIES.md](./ARCHITECTURE-BOUNDARIES.md) and partially
enforced by Ruff `flake8-tidy-imports`.

## Tests

```
tests/unit/          no external services required
tests/integration/   marked `integration`; needs docker compose up -d
```

Run only the fast suite with `uv run pytest tests/unit`, or exclude
integration tests explicitly with `uv run pytest -m "not integration"`.
