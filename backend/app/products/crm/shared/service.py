"""Generic tenant-scoped CRUD service.

Holds the behaviour every CRM entity shares — create with authorship, fetch or
404, patch, soft delete — so each module's service only contains the rules that
are actually specific to it.

Two invariants are enforced here and cannot be opted out of by a subclass:

1. ``organization_id`` is taken from the authenticated principal, never from
   the request body. A client cannot create or move a record into another
   tenant by supplying a different id.
2. Reads go through :meth:`get_or_404`, which filters by organization, so a
   guessed identifier from another tenant is indistinguishable from one that
   does not exist.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Sequence
from typing import Any, TypeVar

from sqlalchemy import ColumnElement

from app.core.exceptions import NotFoundError
from app.products.crm.shared.pagination import PageParams
from app.products.crm.shared.repository import TenantOwnedModel, TenantScopedRepository

ModelT = TypeVar("ModelT", bound=TenantOwnedModel)


class TenantScopedService[ModelT: TenantOwnedModel]:
    """CRUD over one CRM entity, always scoped to a single organization."""

    #: Human-readable name used in 404 messages.
    entity_name: str = "Record"

    def __init__(self, repository: TenantScopedRepository[ModelT], model: type[ModelT]) -> None:
        self._repository = repository
        self._model = model

    # --- Reads -------------------------------------------------------------

    async def get_or_404(self, entity_id: uuid.UUID, organization_id: uuid.UUID) -> ModelT:
        """Fetch a record in the caller's organization, or raise 404.

        A record belonging to another tenant produces the same 404 as one that
        does not exist. Returning 403 instead would confirm the id is real and
        leak the existence of another tenant's data.
        """
        entity = await self._repository.get(entity_id, organization_id)
        if entity is None:
            raise NotFoundError(f"{self.entity_name} not found.")
        return entity

    async def list(
        self,
        organization_id: uuid.UUID,
        *,
        params: PageParams,
        filters: Sequence[ColumnElement[bool]] = (),
    ) -> tuple[Sequence[ModelT], int]:
        return await self._repository.list(organization_id, params=params, filters=filters)

    # --- Writes ------------------------------------------------------------

    async def create(
        self,
        *,
        organization_id: uuid.UUID,
        actor_id: uuid.UUID | None,
        values: dict[str, Any],
    ) -> ModelT:
        """Create a record owned by ``organization_id``.

        ``organization_id`` and the authorship columns are applied after the
        caller's values, so a body attempting to set them is overridden rather
        than honoured.
        """
        payload = dict(values)
        payload.pop("organization_id", None)
        payload.pop("created_by_id", None)
        payload.pop("updated_by_id", None)
        payload.pop("id", None)

        entity = self._model(  # type: ignore[call-arg]
            **payload,
            organization_id=organization_id,
            created_by_id=actor_id,
            updated_by_id=actor_id,
        )
        return await self._repository.add(entity)

    async def update(
        self,
        entity: ModelT,
        *,
        actor_id: uuid.UUID | None,
        values: dict[str, Any],
    ) -> ModelT:
        """Apply a partial update to an already-authorized record.

        The caller must have obtained ``entity`` through :meth:`get_or_404`, so
        organization ownership is established before anything is written.
        """
        for field, value in values.items():
            if field in {"organization_id", "id", "created_by_id", "created_at"}:
                continue
            setattr(entity, field, value)
        entity.updated_by_id = actor_id  # type: ignore[attr-defined]
        await self._repository.flush()
        return entity

    async def soft_delete(
        self, entity: ModelT, *, actor_id: uuid.UUID | None, at: dt.datetime | None = None
    ) -> ModelT:
        """Archive a record. Nothing is physically deleted through the API."""
        entity.updated_by_id = actor_id  # type: ignore[attr-defined]
        return await self._repository.soft_delete(entity, at=at)


__all__ = ["TenantScopedService"]
