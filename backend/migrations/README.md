# Migrations

Alembic migrations for the S3K modular monolith. **One database, one migration
history** shared by the Shared Platform and every product module (ADR-001,
ADR-007) — do not create per-module migration trees.

```bash
uv run alembic current                              # applied revision
uv run alembic revision --autogenerate -m "message" # generate
uv run alembic upgrade head                         # apply
uv run alembic downgrade -1                         # roll back one
```

`env.py` reads the database URL from application settings (`app.core.config`)
and targets `app.core.metadata.target_metadata`, so migrations and the runtime
can never drift apart. No credentials live in `alembic.ini`.

**Autogenerate only sees imported models.** Every new `models.py` must be
imported from `app/core/metadata.py`, or its tables will be silently missing
from the generated revision — and, worse, a later autogenerate will try to drop
them.

`versions/` is empty by design: no Platform or CRM tables exist yet. Tenant
context, shared model mixins and RLS policies are the next Phase 0 task.
