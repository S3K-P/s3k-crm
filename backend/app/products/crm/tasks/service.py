"""Task business rules (plan P2-W18-BE-04).

Two behaviours worth stating:

* ``completed_at`` is **derived, never supplied**. It is stamped when the
  status moves to COMPLETED and cleared when the task reopens, so it can never
  contradict the status it is supposed to describe.
* Polymorphic links are validated against the caller's organization on every
  write, through :mod:`app.products.crm.shared.relations`.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import ColumnElement, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.products.crm.common import CrmEntityType, Priority
from app.products.crm.shared.pagination import PageParams
from app.products.crm.shared.relations import validate_related_entity
from app.products.crm.shared.repository import TenantScopedRepository
from app.products.crm.shared.service import TenantScopedService
from app.products.crm.shared.visibility import RecordVisibility
from app.products.crm.tasks.models import Task, TaskStatus

#: Statuses that mean the task is off someone's plate.
CLOSED_STATUSES: frozenset[TaskStatus] = frozenset(
    {TaskStatus.COMPLETED, TaskStatus.CANCELLED}
)


class TaskService(TenantScopedService[Task]):
    entity_name = "Task"

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(TenantScopedRepository(session, Task), Task)
        self._session = session

    # --- Queries -----------------------------------------------------------

    def build_filters(
        self,
        *,
        search: str | None = None,
        status: TaskStatus | None = None,
        priority: Priority | None = None,
        assigned_to_id: uuid.UUID | None = None,
        related_entity_type: CrmEntityType | None = None,
        related_entity_id: uuid.UUID | None = None,
        open_only: bool = False,
    ) -> list[ColumnElement[bool]]:
        filters: list[ColumnElement[bool]] = []
        if search:
            term = f"%{search.strip().lower()}%"
            filters.append(
                or_(
                    func.lower(Task.title).like(term),
                    func.lower(func.coalesce(Task.description, "")).like(term),
                )
            )
        if status is not None:
            filters.append(Task.status == status)
        if priority is not None:
            filters.append(Task.priority == priority)
        if assigned_to_id is not None:
            filters.append(Task.assigned_to_id == assigned_to_id)
        if related_entity_type is not None:
            filters.append(Task.related_entity_type == related_entity_type)
        if related_entity_id is not None:
            filters.append(Task.related_entity_id == related_entity_id)
        if open_only:
            filters.append(Task.status.not_in(tuple(CLOSED_STATUSES)))
        return filters

    async def list_tasks(
        self,
        organization_id: uuid.UUID,
        *,
        params: PageParams,
        filters: Sequence[ColumnElement[bool]] = (),
        visibility: RecordVisibility | None = None,
    ) -> tuple[Sequence[Task], int]:
        return await self.list(
            organization_id, params=params, filters=filters, visibility=visibility
        )

    async def counts_by_status(self, organization_id: uuid.UUID) -> dict[str, int]:
        """Per-status totals, with every status present even at zero."""
        result = await self._session.execute(
            select(Task.status, func.count())
            .where(Task.organization_id == organization_id, Task.deleted_at.is_(None))
            .group_by(Task.status)
        )
        counts = {status.value: 0 for status in TaskStatus}
        for status, total in result.all():
            counts[status.value] = int(total)
        return counts

    # --- Commands ----------------------------------------------------------

    async def create_task(
        self,
        *,
        organization_id: uuid.UUID,
        actor_id: uuid.UUID | None,
        values: dict[str, Any],
    ) -> Task:
        """Create a task after checking any linked record is reachable."""
        payload = dict(values)
        payload.pop("completed_at", None)

        await validate_related_entity(
            self._session,
            entity_type=payload.get("related_entity_type"),
            entity_id=payload.get("related_entity_id"),
            organization_id=organization_id,
        )

        if payload.get("status") in CLOSED_STATUSES:
            payload["completed_at"] = dt.datetime.now(dt.UTC)

        return await self.create(
            organization_id=organization_id, actor_id=actor_id, values=payload
        )

    async def update_task(
        self,
        task: Task,
        *,
        actor_id: uuid.UUID | None,
        values: dict[str, Any],
    ) -> Task:
        """Patch a task, keeping ``completed_at`` consistent with the status."""
        payload = dict(values)
        payload.pop("completed_at", None)

        # A partial update may move either half of the link, so validate the
        # resulting pair rather than only what was supplied.
        if "related_entity_type" in payload or "related_entity_id" in payload:
            await validate_related_entity(
                self._session,
                entity_type=payload.get("related_entity_type", task.related_entity_type),
                entity_id=payload.get("related_entity_id", task.related_entity_id),
                organization_id=task.organization_id,
            )

        new_status = payload.get("status")
        if new_status is not None and new_status != task.status:
            payload["completed_at"] = (
                dt.datetime.now(dt.UTC) if new_status in CLOSED_STATUSES else None
            )

        return await self.update(task, actor_id=actor_id, values=payload)

    async def set_status(
        self, task: Task, *, status: TaskStatus, actor_id: uuid.UUID | None
    ) -> Task:
        """Move a task to ``status``, stamping or clearing completion."""
        return await self.update_task(task, actor_id=actor_id, values={"status": status})


__all__ = ["CLOSED_STATUSES", "TaskService"]
