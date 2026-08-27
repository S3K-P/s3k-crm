# S3K CRM

Monorepo for the S3K Enterprise Platform, starting with the S3K CRM product.

## Structure

```
├── frontend/   Next.js UI (port 3000, npm workspace)
├── backend/    FastAPI modular monolith (port 8000, uv project)
└── docs/       Architecture decision records and implementation plan
```

The frontend is a JavaScript npm workspace. The backend is a Python project managed
by [uv](https://docs.astral.sh/uv/) and is intentionally **not** an npm workspace.

## Prerequisites

| Tool | Version |
|------|---------|
| Node.js | 20+ |
| Python | 3.13 (installed automatically by `uv`) |
| uv | 0.5+ |
| Docker | with Compose v2 |

## Quick start

### 1. Local infrastructure (PostgreSQL 18 + Redis 7 + MinIO)

```bash
cp .env.example .env      # then set POSTGRES_PASSWORD and STORAGE_SECRET_ACCESS_KEY
docker compose up -d
docker compose ps
```

MinIO provides S3-compatible object storage for attachments (ADR-014).
Production uses Cloudflare R2; MinIO speaks the same API, so the application
runs the identical `boto3` code path against either and only the endpoint and
credentials differ. The `minio-init` container creates the bucket and exits —
seeing it in `Exited (0)` is the expected state. Its console is on
<http://localhost:9001>.

The attachment integration tests skip themselves when storage is unreachable,
so a backend suite that reports skips there means MinIO is not running.

### 2. Backend

```bash
cd backend
cp .env.example .env
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 8000
```

`DATABASE_URL` names `s3k_app`, **not** the `POSTGRES_USER` from the root
`.env`. That user is a superuser, and a superuser is exempt from every
row-level security policy — running the application as it removes tenant
isolation silently. `infra/postgres/init/` creates the ordinary role when the
postgres volume is first initialised; on an older volume, see
[backend/README.md](./backend/README.md#the-application-does-not-connect-as-postgres_user).

Then create the first organization and its administrator:

```bash
BOOTSTRAP_PASSWORD='<a strong password>' uv run python -m app.bootstrap --organization "Acme" --email admin@acme.example
```

Health checks:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/health/ready
```

See [backend/README.md](./backend/README.md) for module structure, migrations, and
quality gates.

### 3. Frontend

```bash
npm install
cd frontend
npm run dev
```

## Root scripts

| Script | Purpose |
|--------|---------|
| `npm run dev` | Frontend dev server |
| `npm run dev:backend` | FastAPI dev server via `uv` |
| `npm run backend:sync` | `uv sync` in `backend/` |
| `npm run backend:lint` | Ruff |
| `npm run backend:typecheck` | mypy strict |
| `npm run backend:test` | pytest |
| `npm run infra:up` / `infra:down` | Docker Compose infrastructure |

## Architecture

The platform is a **modular monolith**: a Shared Platform layer (identity,
organizations, authorization, documents, audit, notifications) and product modules
(CRM first). See:

- [docs/architecture/16-ARCHITECTURE-DECISION-RECORDS.md](./docs/architecture/16-ARCHITECTURE-DECISION-RECORDS.md)
- [docs/architecture/18-MASTER-IMPLEMENTATION-PLAN.md](./docs/architecture/18-MASTER-IMPLEMENTATION-PLAN.md)
- [backend/ARCHITECTURE-BOUNDARIES.md](./backend/ARCHITECTURE-BOUNDARIES.md)

## Frontend docs

See [frontend/README.md](./frontend/README.md) for UI template details, theming, and
page-building guides.
