"""Generic tenant-scoped repository.

Every CRM entity shares the same access pattern — filter by organization,
exclude soft-deleted rows, paginate, sort — so it is implemented once here.

**This class is the application-level half of tenant isolation.** PostgreSQL
RLS is the backstop that makes a mistake here non-fatal, but defence in depth
means the query must be correct on its own: every statement below filters on
``organization_id`` explicitly, and there is no code path that omits it.

The generic parameter is bound to a model carrying both ``organization_id``
and ``deleted_at``, so a table without them cannot be used with it by mistake.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Sequence
from typing import Any, Protocol, TypeVar, cast

from sqlalchemy import ColumnElement, Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute, class_mapper

from app.products.crm.shared.pagination import PageParams


class TenantOwnedModel(Protocol):
    """Structural type for a row this repository can manage."""

    id: Any
    organization_id: Any
    deleted_at: Any
    created_at: Any


ModelT = TypeVar("ModelT", bound=TenantOwnedModel)


class TenantScopedRepository[ModelT: TenantOwnedModel]:
    """Organization-filtered CRUD for one CRM table."""

    def __init__(self, session: AsyncSession, model: type[ModelT]) -> None:
        self._session = session
        self._model = model

    # --- Query construction ------------------------------------------------

    def _base_query(
        self, organization_id: uuid.UUID, *, include_deleted: bool = False
    ) -> Select[Any]:
        """The only place a SELECT for this table is started.

        Both predicates are applied unconditionally so no caller can forget
        either one.
        """
        statement = select(self._model).where(self._model.organization_id == organization_id)
        if not include_deleted:
            statement = statement.where(self._model.deleted_at.is_(None))
        return statement

    def _sortable_columns(self) -> dict[str, InstrumentedAttribute[Any]]:
        """Mapped columns of this model, keyed by name.

        Computed from the mapper rather than hand-listed so a new column is
        sortable automatically, and — more importantly — so a name that is not
        a real column can never reach the ORDER BY clause.
        """
        mapper = class_mapper(cast("type[Any]", self._model))
        return {
            attribute.key: getattr(self._model, attribute.key)
            for attribute in mapper.column_attrs
        }

    def _apply_sort(self, statement: Select[Any], params: PageParams) -> Select[Any]:
        """Sort by a mapped column, falling back to newest first.

        ``sort_by`` arrives from the query string. It is resolved against the
        mapper's known columns and silently ignored when it does not match, so
        an attacker-supplied value cannot be injected into the SQL.
        """
        columns = self._sortable_columns()
        column = columns.get(params.sort_by) if params.sort_by else None
        if column is None:
            column = self._model.created_at
        return statement.order_by(column.desc() if params.sort_dir == "desc" else column.asc())

    # --- Reads -------------------------------------------------------------

    async def get(
        self, entity_id: uuid.UUID, organization_id: uuid.UUID, *, include_deleted: bool = False
    ) -> ModelT | None:
        """Fetch one row **within the organization**.

        Passing another tenant's id returns ``None``, which callers turn into
        404 — this is the primary defence against insecure direct object
        reference.
        """
        result = await self._session.execute(
            self._base_query(organization_id, include_deleted=include_deleted).where(
                self._model.id == entity_id
            )
        )
        return result.scalar_one_or_none()

    async def list(
        self,
        organization_id: uuid.UUID,
        *,
        params: PageParams,
        filters: Sequence[ColumnElement[bool]] = (),
    ) -> tuple[Sequence[ModelT], int]:
        """Return one page of rows plus the total matching count."""
        statement = self._base_query(organization_id)
        for condition in filters:
            statement = statement.where(condition)

        count_statement = select(func.count()).select_from(statement.subquery())
        total = int((await self._session.execute(count_statement)).scalar_one())

        statement = self._apply_sort(statement, params).limit(params.limit).offset(params.offset)
        result = await self._session.execute(statement)
        return result.scalars().all(), total

    async def count(
        self, organization_id: uuid.UUID, *, filters: Sequence[ColumnElement[bool]] = ()
    ) -> int:
        statement = self._base_query(organization_id)
        for condition in filters:
            statement = statement.where(condition)
        result = await self._session.execute(select(func.count()).select_from(statement.subquery()))
        return int(result.scalar_one())

    async def exists(self, entity_id: uuid.UUID, organization_id: uuid.UUID) -> bool:
        return await self.get(entity_id, organization_id) is not None

    # --- Writes ------------------------------------------------------------

    async def add(self, entity: ModelT) -> ModelT:
        self._session.add(entity)
        await self._session.flush()
        return entity

    async def soft_delete(self, entity: ModelT, *, at: dt.datetime | None = None) -> ModelT:
        """Mark a row deleted. Rows are never physically removed by the API."""
        entity.deleted_at = at or dt.datetime.now(dt.UTC)
        await self._session.flush()
        return entity

    async def restore(self, entity: ModelT) -> ModelT:
        entity.deleted_at = None
        await self._session.flush()
        return entity

    async def flush(self) -> None:
        await self._session.flush()


__all__ = ["TenantOwnedModel", "TenantScopedRepository"]
