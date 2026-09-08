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

Calling :func:`enable_rls` is not the same as having called it everywhere it
was needed. :mod:`app.core.schema_audit` checks the finished schema against the
database's own catalogues and fails on any tenant-scoped table this module was
never pointed at.
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


def tenant_policy_predicate(
    column: str = "organization_id", *, optional_tenant: bool = False
) -> str:
    """Return the SQL predicate isolating rows to the current tenant.

    ``NULLIF(..., '')`` maps "setting never assigned" to NULL, which makes the
    comparison NULL and therefore excludes the row. Fail closed.

    ``optional_tenant`` widens that by exactly one case, for tables holding a
    few rows that genuinely belong to no organization — see
    :func:`enable_rls`. ``IS NOT DISTINCT FROM`` is NULL-aware equality: a row
    with no organization matches only a session with no organization, and a
    row with one matches only that organization. Both directions still fail
    closed, which a plain ``=`` cannot express because ``NULL = NULL`` is NULL.
    """
    setting = f"NULLIF(current_setting('{TENANT_SETTING}', true), '')::uuid"
    if optional_tenant:
        return f"{column} IS NOT DISTINCT FROM {setting}"
    return f"{column} = {setting}"


def enable_rls(
    connection: Connection,
    table: str,
    *,
    schema: str,
    column: str = "organization_id",
    policy_name: str | None = None,
    optional_tenant: bool = False,
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
        optional_tenant: allow ``column`` to be NULL, meaning "belongs to no
            organization", and admit such a row only to a session that has no
            organization in scope. Pass this **only** for a table that has a
            genuine untenanted case and say so in its model docstring: it is
            checked separately and more strictly by the schema audit, which
            requires the resulting policy to be NULL-aware in both directions
            rather than accepting a nullable tenant column on trust.

            ``platform.email_deliveries`` is the case that exists: a
            password-reset message is addressed to a person's global identity,
            which may belong to no organization at all, and the log of it must
            still be written — the unique index on ``outbox_event_id`` is what
            stops a retried event sending the link twice.
    """
    policy = policy_name or f"{table}_tenant_isolation"
    qualified = f'"{schema}"."{table}"'
    predicate = tenant_policy_predicate(column, optional_tenant=optional_tenant)

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
