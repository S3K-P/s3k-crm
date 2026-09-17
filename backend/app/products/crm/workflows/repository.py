"""Data access for ``crm.workflow_rules`` and ``crm.workflow_runs``.

The only layer permitted to construct SQLAlchemy queries against either — see
``ARCHITECTURE-BOUNDARIES.md`` rule 2, restated per module.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.products.crm.shared.pagination import PageParams
from app.products.crm.shared.repository import TenantScopedRepository
from app.products.crm.workflows.models import WorkflowEntityType, WorkflowRule, WorkflowRun


class WorkflowRuleRepository(TenantScopedRepository[WorkflowRule]):
    """Queries over ``crm.workflow_rules``."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, WorkflowRule)

    async def active_for_entity_type(
        self, organization_id: uuid.UUID, entity_type: WorkflowEntityType
    ) -> Sequence[WorkflowRule]:
        """Every active rule for ``entity_type``, in execution order.

        The engine's hot-path read: one per matching outbox event. Further
        narrowing by ``trigger_type`` happens in Python
        (`.conditions.rule_matches_trigger`) rather than in this query — an
        organization's rule count for one entity is small enough that the
        difference is noise, and keeping the matching logic in one pure,
        unit-testable function is worth more than a marginally smaller result
        set.
        """
        result = await self._session.execute(
            select(WorkflowRule)
            .where(
                WorkflowRule.organization_id == organization_id,
                WorkflowRule.deleted_at.is_(None),
                WorkflowRule.entity_type == entity_type,
                WorkflowRule.is_active.is_(True),
            )
            .order_by(WorkflowRule.position.asc(), WorkflowRule.created_at.asc())
        )
        return result.scalars().all()

    async def all_active_scheduled(self, organization_id: uuid.UUID) -> Sequence[WorkflowRule]:
        """Active ``SCHEDULED``/``TASK_DUE`` rules, for the periodic scan."""
        result = await self._session.execute(
            select(WorkflowRule)
            .where(
                WorkflowRule.organization_id == organization_id,
                WorkflowRule.deleted_at.is_(None),
                WorkflowRule.is_active.is_(True),
                WorkflowRule.trigger_type.in_(("SCHEDULED", "TASK_DUE")),
            )
            .order_by(WorkflowRule.position.asc())
        )
        return result.scalars().all()

    async def name_taken(
        self, organization_id: uuid.UUID, name: str, *, excluding: uuid.UUID | None = None
    ) -> bool:
        statement = (
            select(func.count())
            .select_from(WorkflowRule)
            .where(
                WorkflowRule.organization_id == organization_id,
                WorkflowRule.deleted_at.is_(None),
                func.lower(WorkflowRule.name) == name.lower(),
            )
        )
        if excluding is not None:
            statement = statement.where(WorkflowRule.id != excluding)
        return int((await self._session.execute(statement)).scalar_one()) > 0


class WorkflowRunRepository:
    """Queries over ``crm.workflow_runs`` — append-only, so no update helpers."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_for_organization(
        self,
        organization_id: uuid.UUID,
        *,
        params: PageParams,
        filters: Sequence[ColumnElement[bool]] = (),
    ) -> tuple[Sequence[WorkflowRun], int]:
        base = select(WorkflowRun).where(WorkflowRun.organization_id == organization_id, *filters)
        total = int(
            (
                await self._session.execute(
                    select(func.count()).select_from(base.subquery())
                )
            ).scalar_one()
        )
        rows = await self._session.execute(
            base.order_by(WorkflowRun.created_at.desc())
            .limit(params.page_size)
            .offset(params.offset)
        )
        return rows.scalars().all(), total

    async def get(self, run_id: uuid.UUID, organization_id: uuid.UUID) -> WorkflowRun | None:
        result = await self._session.execute(
            select(WorkflowRun).where(
                WorkflowRun.id == run_id, WorkflowRun.organization_id == organization_id
            )
        )
        return result.scalar_one_or_none()


__all__ = ["WorkflowRuleRepository", "WorkflowRunRepository"]
