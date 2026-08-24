"""Data access for the documents module.

Every statement filters on ``organization_id`` explicitly. RLS on
``platform.attachments`` is the backstop, not the plan (doc 13, defence in
depth): the query is written to be correct on its own, so a connection that
somehow escaped its tenant scope still cannot reach another organization's
attachment metadata through this class.

Soft-deleted rows are excluded from every read unless a caller explicitly asks
for them via ``include_deleted``. Nothing does today: an attachment that has
been deleted is gone as far as the API is concerned, so deleting one twice is a
404 on the second attempt. The flag exists for a future restore or audit-detail
path that needs to name a row it has already archived.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Sequence

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import PageParams
from app.platform.documents.models import Attachment, AttachmentStatus


class AttachmentRepository:
    """Tenant-scoped access to ``platform.attachments``."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @property
    def session(self) -> AsyncSession:
        """The session this repository writes through.

        Exposed so the service can append an audit record on the same
        transaction as the metadata change it describes.
        """
        return self._session

    # --- Reads -------------------------------------------------------------

    def _base_query(
        self, organization_id: uuid.UUID, *, include_deleted: bool = False
    ) -> Select[tuple[Attachment]]:
        statement = select(Attachment).where(
            Attachment.organization_id == organization_id
        )
        if not include_deleted:
            statement = statement.where(Attachment.deleted_at.is_(None))
        return statement

    async def get(
        self,
        attachment_id: uuid.UUID,
        organization_id: uuid.UUID,
        *,
        include_deleted: bool = False,
    ) -> Attachment | None:
        """One row **within the organization**.

        Another tenant's id returns ``None``, which the service turns into 404
        — the same treatment every other module gives a cross-tenant
        identifier, and the reason a prober cannot tell "not yours" from "not
        there".
        """
        result = await self._session.execute(
            self._base_query(organization_id, include_deleted=include_deleted).where(
                Attachment.id == attachment_id
            )
        )
        return result.scalar_one_or_none()

    async def list_for_entity(
        self,
        organization_id: uuid.UUID,
        *,
        entity_type: str,
        entity_id: uuid.UUID,
        params: PageParams,
        include_pending: bool = False,
    ) -> tuple[Sequence[Attachment], int]:
        """One page of a record's attachments, newest first.

        ``PENDING`` rows are hidden by default. One exists for every upload URL
        ever issued, including those the browser abandoned, so showing them
        would put files that do not exist in front of the user.
        """
        statement = self._base_query(organization_id).where(
            Attachment.entity_type == entity_type,
            Attachment.entity_id == entity_id,
        )
        if not include_pending:
            statement = statement.where(Attachment.status == AttachmentStatus.ACTIVE)

        total = int(
            (
                await self._session.execute(
                    select(func.count()).select_from(statement.subquery())
                )
            ).scalar_one()
        )

        ordered = statement.order_by(Attachment.created_at.desc(), Attachment.id.desc())
        result = await self._session.execute(
            ordered.limit(params.limit).offset(params.offset)
        )
        return result.scalars().all(), total

    async def count_for_entity(
        self, organization_id: uuid.UUID, *, entity_type: str, entity_id: uuid.UUID
    ) -> int:
        result = await self._session.execute(
            select(func.count())
            .select_from(Attachment)
            .where(
                Attachment.organization_id == organization_id,
                Attachment.entity_type == entity_type,
                Attachment.entity_id == entity_id,
                Attachment.deleted_at.is_(None),
                Attachment.status == AttachmentStatus.ACTIVE,
            )
        )
        return int(result.scalar_one())

    # --- Writes ------------------------------------------------------------

    async def add(self, attachment: Attachment) -> Attachment:
        self._session.add(attachment)
        await self._session.flush()
        return attachment

    async def flush(self) -> None:
        await self._session.flush()

    async def delete_row(self, attachment: Attachment) -> None:
        """Physically remove a metadata row.

        Used only for a ``PENDING`` row whose object never arrived, or whose
        upload was rejected at confirm time. Such a row describes nothing that
        ever existed, so keeping it soft-deleted would leave the trail claiming
        a file was attached and removed when neither happened.
        """
        await self._session.delete(attachment)
        await self._session.flush()

    async def soft_delete(
        self, attachment: Attachment, *, at: dt.datetime | None = None
    ) -> Attachment:
        attachment.deleted_at = at or dt.datetime.now(dt.UTC)
        await self._session.flush()
        return attachment


__all__ = ["AttachmentRepository"]
