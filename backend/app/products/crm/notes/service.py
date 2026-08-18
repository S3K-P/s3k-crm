"""Note business rules (plan P2-W18-BE-06).

Notes carry a visibility level, and this module is where it is enforced:

* ``PRIVATE`` — only the author may read or edit it.
* ``TEAM`` / ``ORGANIZATION`` — any member of the organization who can view the
  notes module.

The filter is applied **inside the SQL query**, not to the result set after
fetching. Post-filtering would mean another user's private note travels out of
the database and through the application before being dropped, and the row
count would still leak its existence.

Editing is restricted to the author regardless of visibility: a note is a
personal record of what someone observed, and letting a colleague rewrite it
would make the audit trail meaningless.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Any

from fastapi import status
from sqlalchemy import ColumnElement, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError, NotFoundError
from app.products.crm.common import CrmEntityType
from app.products.crm.notes.models import Note, NoteVisibility
from app.products.crm.shared.pagination import PageParams
from app.products.crm.shared.relations import validate_related_entity
from app.products.crm.shared.repository import TenantScopedRepository
from app.products.crm.shared.service import TenantScopedService


class NoteNotEditableError(AppError):
    """Only the author may change or remove a note."""

    status_code = status.HTTP_403_FORBIDDEN
    code = "note_not_editable"
    message = "Only the author can change this note."


class NoteService(TenantScopedService[Note]):
    entity_name = "Note"

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(TenantScopedRepository(session, Note), Note)
        self._session = session

    # --- Queries -----------------------------------------------------------

    @staticmethod
    def visibility_filter(viewer_id: uuid.UUID | None) -> ColumnElement[bool]:
        """Restrict a query to notes ``viewer_id`` is allowed to see.

        Anything not private is shared; a private note is visible only to the
        person who wrote it.
        """
        shared = Note.visibility != NoteVisibility.PRIVATE
        if viewer_id is None:
            return shared
        own_private = and_(
            Note.visibility == NoteVisibility.PRIVATE, Note.author_id == viewer_id
        )
        return or_(shared, own_private)

    def build_filters(
        self,
        *,
        viewer_id: uuid.UUID | None,
        related_entity_type: CrmEntityType | None = None,
        related_entity_id: uuid.UUID | None = None,
    ) -> list[ColumnElement[bool]]:
        filters: list[ColumnElement[bool]] = [self.visibility_filter(viewer_id)]
        if related_entity_type is not None:
            filters.append(Note.related_entity_type == related_entity_type)
        if related_entity_id is not None:
            filters.append(Note.related_entity_id == related_entity_id)
        return filters

    async def list_notes(
        self,
        organization_id: uuid.UUID,
        *,
        params: PageParams,
        filters: Sequence[ColumnElement[bool]] = (),
    ) -> tuple[Sequence[Note], int]:
        return await self.list(organization_id, params=params, filters=filters)

    async def get_visible_or_404(
        self, note_id: uuid.UUID, organization_id: uuid.UUID, *, viewer_id: uuid.UUID | None
    ) -> Note:
        """Fetch a note the viewer is allowed to read, or 404.

        Someone else's private note produces the same 404 as a note that does
        not exist — confirming it were there would defeat the point of marking
        it private.
        """
        note = await self.get_or_404(note_id, organization_id)
        if note.visibility is NoteVisibility.PRIVATE and note.author_id != viewer_id:
            raise NotFoundError(f"{self.entity_name} not found.")
        return note

    # --- Commands ----------------------------------------------------------

    async def create_note(
        self,
        *,
        organization_id: uuid.UUID,
        actor_id: uuid.UUID | None,
        values: dict[str, Any],
    ) -> Note:
        """Attach a note to a record in the caller's organization."""
        payload = dict(values)
        await validate_related_entity(
            self._session,
            entity_type=payload.get("related_entity_type"),
            entity_id=payload.get("related_entity_id"),
            organization_id=organization_id,
        )
        # Authorship is taken from the principal, never from the body.
        payload["author_id"] = actor_id
        return await self.create(
            organization_id=organization_id, actor_id=actor_id, values=payload
        )

    async def update_note(
        self, note: Note, *, actor_id: uuid.UUID | None, values: dict[str, Any]
    ) -> Note:
        """Edit a note. Authors only.

        Raises:
            NoteNotEditableError: the caller did not write it.
        """
        self._require_author(note, actor_id)
        payload = dict(values)
        # The link is fixed at creation: moving a note to another record would
        # silently rewrite history on both.
        payload.pop("related_entity_type", None)
        payload.pop("related_entity_id", None)
        payload.pop("author_id", None)
        return await self.update(note, actor_id=actor_id, values=payload)

    async def delete_note(self, note: Note, *, actor_id: uuid.UUID | None) -> Note:
        """Archive a note. Authors only.

        Raises:
            NoteNotEditableError: the caller did not write it.
        """
        self._require_author(note, actor_id)
        return await self.soft_delete(note, actor_id=actor_id)

    # --- Internals ---------------------------------------------------------

    @staticmethod
    def _require_author(note: Note, actor_id: uuid.UUID | None) -> None:
        if note.author_id is not None and note.author_id != actor_id:
            raise NoteNotEditableError


__all__ = ["NoteNotEditableError", "NoteService"]
