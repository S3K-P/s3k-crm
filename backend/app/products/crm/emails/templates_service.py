"""Template lifecycle: save, share, edit, retire.

A separate service from :class:`~app.products.crm.emails.service.EmailService`
because it is a separate entity with a separate table, and
:class:`~app.products.crm.shared.service.TenantScopedService` is generic over
exactly one model. Putting both through one service would mean one of them
losing the inherited create/update/soft-delete-with-audit path, which is the
part nobody should be reimplementing.

The visibility rule is the one notes already use: shared templates belong to
the organization, a private one belongs to its author, and editing is the
author's regardless. A colleague's private template is a 404 rather than a
403 — confirming it exists would defeat the point of it being private.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Any

from fastapi import status
from sqlalchemy import ColumnElement, and_, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError, ValidationFailedError
from app.products.crm.emails.models import EmailTemplate
from app.products.crm.shared.pagination import PageParams
from app.products.crm.shared.repository import TenantScopedRepository
from app.products.crm.shared.service import TenantScopedService


class TemplateNotEditableError(AppError):
    """Only the author may change or retire a template."""

    status_code = status.HTTP_403_FORBIDDEN
    code = "email_template_not_editable"
    message = "Only the author can change this template."


class DuplicateTemplateNameError(ValidationFailedError):
    """Another live template in this organization already has that name."""

    code = "email_template_name_taken"
    message = "A template with that name already exists."


class EmailTemplateService(TenantScopedService[EmailTemplate]):
    """CRUD over ``crm.email_templates``."""

    entity_name = "Template"

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(TenantScopedRepository(session, EmailTemplate), EmailTemplate)
        self._session = session

    # The table is `email_templates`; the permission module is `emails`. Both
    # this and the entity type are stated rather than derived, so the audit
    # trail files a template under the same module as the mail it composes.
    @property
    def audit_module(self) -> str:
        return "emails"

    @property
    def audit_entity_type(self) -> str:
        return "EMAIL_TEMPLATE"

    @staticmethod
    def visibility_filter(viewer_id: uuid.UUID | None) -> ColumnElement[bool]:
        """Restrict a query to templates ``viewer_id`` may see.

        Applied **inside the SQL**, not to the result set. Post-filtering
        would mean a colleague's private template travelling out of the
        database before being dropped, and the row count would still betray
        that it exists.
        """
        shared = EmailTemplate.is_shared.is_(True)
        if viewer_id is None:
            return shared
        own_private = and_(
            EmailTemplate.is_shared.is_(False), EmailTemplate.owner_id == viewer_id
        )
        return or_(shared, own_private)

    async def list_templates(
        self,
        organization_id: uuid.UUID,
        *,
        params: PageParams,
        viewer_id: uuid.UUID | None,
        category: str | None = None,
    ) -> tuple[Sequence[EmailTemplate], int]:
        filters: list[ColumnElement[bool]] = [self.visibility_filter(viewer_id)]
        if category:
            filters.append(EmailTemplate.category == category)
        return await self.list(organization_id, params=params, filters=filters)

    async def create_template(
        self,
        *,
        organization_id: uuid.UUID,
        actor_id: uuid.UUID | None,
        values: dict[str, Any],
    ) -> EmailTemplate:
        """Save a template.

        Raises:
            DuplicateTemplateNameError: the name is taken by a live template.
        """
        payload = dict(values)
        # Ownership is the principal's, never the body's.
        payload["owner_id"] = actor_id
        try:
            return await self.create(
                organization_id=organization_id, actor_id=actor_id, values=payload
            )
        except IntegrityError as failure:
            # The partial unique index is the authority, not a prior SELECT: a
            # check-then-insert loses a race between two people saving the same
            # name, and the loser gets a 500 instead of a message they can act
            # on.
            await self._session.rollback()
            raise DuplicateTemplateNameError(
                details={"name": payload.get("name")}
            ) from failure

    async def update_template(
        self,
        template: EmailTemplate,
        *,
        actor_id: uuid.UUID | None,
        values: dict[str, Any],
    ) -> EmailTemplate:
        """Edit a template. Authors only.

        Raises:
            TemplateNotEditableError: the caller did not write it.
            DuplicateTemplateNameError: the new name is taken.
        """
        self._require_author(template, actor_id)
        payload = dict(values)
        payload.pop("owner_id", None)
        try:
            return await self.update(template, actor_id=actor_id, values=payload)
        except IntegrityError as failure:
            await self._session.rollback()
            raise DuplicateTemplateNameError(
                details={"name": payload.get("name")}
            ) from failure

    async def archive_template(
        self, template: EmailTemplate, *, actor_id: uuid.UUID | None
    ) -> EmailTemplate:
        """Retire a template. Authors only.

        Soft, so the name becomes available again — the unique index is
        partial on ``deleted_at IS NULL`` — while every message composed from
        it keeps its ``template_id`` and its history.
        """
        self._require_author(template, actor_id)
        return await self.soft_delete(template, actor_id=actor_id)

    @staticmethod
    def _require_author(template: EmailTemplate, actor_id: uuid.UUID | None) -> None:
        if template.owner_id is not None and template.owner_id != actor_id:
            raise TemplateNotEditableError


__all__ = [
    "DuplicateTemplateNameError",
    "EmailTemplateService",
    "TemplateNotEditableError",
]
