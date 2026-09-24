"""Relabel existing opportunity currency codes from USD to INR.

Revision ID: 20260923_0100
Revises: 20260922_0100
Create Date: 2026-09-23 01:00:00.000000

``20260922_0100`` made ``INR`` the default for *new* opportunities. Rows
written before it still carry ``USD``, which is what the API reports as
``pipeline_currency`` / ``won_revenue_currency``. This finishes the move: the
code on the row is relabelled, and nothing else.

**No amount is converted.** Only the three-letter code changes; every
``deal_value`` is left exactly as stored. This is the same statement the
product makes on screen — the CRM's money is rupees, and always was, whatever
the column said.

``updated_at`` is untouched: its ``onupdate`` is declared on the ORM model, not
as a database trigger, so a relabelled deal does not surface as "just edited".

**Tenant by tenant, not set-based.** ``crm.opportunities`` has FORCE ROW LEVEL
SECURITY, and a migration runs as whatever role ``DATABASE_URL`` names — for
CI and local runs a ``NOSUPERUSER NOBYPASSRLS`` role. With no
``app.current_org_id`` set, the policy's ``NULLIF(current_setting(...), '')``
is NULL, so a single cross-tenant ``UPDATE`` matches **zero rows and raises
nothing**: it would appear to succeed everywhere and actually move nobody
except under a superuser. So this iterates ``platform.organizations`` (which
is RLS-exempt), sets the tenant for each, and still filters on
``organization_id`` explicitly so a superuser run — which bypasses the policy
— stays scoped to the same rows.

**Reversibility.** ``downgrade`` is the mirror image: ``INR`` back to ``USD``,
by the same tenant walk. On a database this revision relabelled, that restores
the previous state exactly. The one thing it cannot know is which rows were
*already* ``INR`` beforehand, or were created as ``INR`` after the upgrade —
those are relabelled to ``USD`` too. Note it before downgrading a database
that has been running on ``INR``.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260923_0100"
down_revision: str | Sequence[str] | None = "20260922_0100"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TENANT_SETTING = "app.current_org_id"

_RELABEL = sa.text(
    """
    UPDATE crm.opportunities
       SET currency = CAST(:to_code AS varchar)
     WHERE organization_id = CAST(:org AS uuid)
       AND currency = CAST(:from_code AS varchar)
    """
)


def _relabel_every_tenant(*, from_code: str, to_code: str) -> None:
    connection = op.get_bind()

    previous = connection.execute(
        sa.text(f"SELECT current_setting('{TENANT_SETTING}', true)")
    ).scalar()

    organization_ids = (
        connection.execute(sa.text("SELECT id FROM platform.organizations")).scalars().all()
    )
    for organization_id in organization_ids:
        connection.execute(
            sa.text(f"SELECT set_config('{TENANT_SETTING}', CAST(:org AS text), true)"),
            {"org": str(organization_id)},
        )
        connection.execute(
            _RELABEL,
            {"org": str(organization_id), "from_code": from_code, "to_code": to_code},
        )

    # Restored deliberately outside a ``finally``: an aborted transaction would
    # raise here and bury the real error.
    connection.execute(
        sa.text(f"SELECT set_config('{TENANT_SETTING}', CAST(:prev AS text), true)"),
        {"prev": previous or ""},
    )


def upgrade() -> None:
    _relabel_every_tenant(from_code="USD", to_code="INR")


def downgrade() -> None:
    _relabel_every_tenant(from_code="INR", to_code="USD")
