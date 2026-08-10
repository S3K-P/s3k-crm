"""Row-Level Security helpers for Alembic migrations (ADR-007, doc 13).

Every tenant-scoped table gets the same policy shape:

    organization_id = current_setting('app.current_org_id')::uuid

which the per-request tenant context sets inside the transaction
(:mod:`app.core.tenant`, :mod:`app.core.database`).

Two details are easy to get wrong and both are handled here:

1. **FORCE.** ``ENABLE ROW LEVEL SECURITY`` alone does not apply to the table's
   owner, and the application usually *is* the owner. ``FORCE`` closes that
   hole.
2. **Unset context.** ``current_setting('app.current_org_id')`` raises if the
   setting was never assigned. Policies use the two-argument form with
   ``NULLIF``, so a query with no tenant context returns **zero rows** instead
   of erroring or, far worse, returning everything.

Superusers and roles with ``BYPASSRLS`` ignore policies entirely. The runtime
must therefore connect as an ordinary role — see :func:`role_bypasses_rls`.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.core.models import TENANT_SETTING

__all__ = [
    "TENANT_SETTING",
    "disable_rls",
    "enable_rls",
    "role_bypasses_rls",
    "tenant_policy_predicate",
]


def tenant_policy_predicate(column: str = "organization_id") -> str:
    """Return the SQL predicate isolating rows to the current tenant.

    ``NULLIF(..., '')`` maps "setting never assigned" to NULL, which makes the
    comparison NULL and therefore excludes the row. Fail closed.
    """
    return f"{column} = NULLIF(current_setting('{TENANT_SETTING}', true), '')::uuid"


def enable_rls(
    connection: Connection,
    table: str,
    *,
    schema: str,
    column: str = "organization_id",
    policy_name: str | None = None,
) -> None:
    """Enable and force tenant RLS on ``schema.table``.

    Creates a single ``FOR ALL`` policy used for both reads (``USING``) and
    writes (``WITH CHECK``), so a tenant can neither read nor insert rows
    belonging to another organization.

    Args:
        connection: the migration's connection.
        table: table name, without schema.
        schema: schema name (``platform`` or ``crm``).
        column: tenant discriminator column.
        policy_name: defaults to ``<table>_tenant_isolation``.
    """
    policy = policy_name or f"{table}_tenant_isolation"
    qualified = f'"{schema}"."{table}"'
    predicate = tenant_policy_predicate(column)

    connection.execute(text(f"ALTER TABLE {qualified} ENABLE ROW LEVEL SECURITY"))
    # Without FORCE the owning role silently bypasses the policy.
    connection.execute(text(f"ALTER TABLE {qualified} FORCE ROW LEVEL SECURITY"))
    connection.execute(text(f'DROP POLICY IF EXISTS "{policy}" ON {qualified}'))
    connection.execute(
        text(
            f'CREATE POLICY "{policy}" ON {qualified} '
            f"FOR ALL USING ({predicate}) WITH CHECK ({predicate})"
        )
    )


def disable_rls(
    connection: Connection,
    table: str,
    *,
    schema: str,
    policy_name: str | None = None,
) -> None:
    """Reverse :func:`enable_rls`, keeping migrations reversible."""
    policy = policy_name or f"{table}_tenant_isolation"
    qualified = f'"{schema}"."{table}"'

    connection.execute(text(f'DROP POLICY IF EXISTS "{policy}" ON {qualified}'))
    connection.execute(text(f"ALTER TABLE {qualified} NO FORCE ROW LEVEL SECURITY"))
    connection.execute(text(f"ALTER TABLE {qualified} DISABLE ROW LEVEL SECURITY"))


def role_bypasses_rls(connection: Connection) -> bool:
    """Return whether the connected role ignores RLS policies.

    ``True`` means tenant isolation is **not** being enforced for this
    connection, regardless of the policies on the tables. Used by the startup
    security check to make a misconfigured deployment loud.
    """
    result = connection.execute(
        text("SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname = current_user")
    )
    return bool(result.scalar())
