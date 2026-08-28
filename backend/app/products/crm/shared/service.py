"""Generic tenant-scoped CRUD service.

Holds the behaviour every CRM entity shares — create with authorship, fetch or
404, patch, soft delete — so each module's service only contains the rules that
are actually specific to it.

Three invariants are enforced here and cannot be opted out of by a subclass:

1. ``organization_id`` is taken from the authenticated principal, never from
   the request body. A client cannot create or move a record into another
   tenant by supplying a different id.
2. Reads go through :meth:`get_or_404`, which filters by organization, so a
   guessed identifier from another tenant is indistinguishable from one that
   does not exist.
3. **Every write appends an audit record**, in the same transaction as the
   change. This is the single place CRM auditing happens: all nine entity
   services inherit from here, so there is no per-controller audit call to
   forget on the next module, and no way to add a create/update/delete path
   that silently records nothing (`P1-W08-BE-03`, backend DoD §2.4).

   Same transaction is the point of it. If the change rolls back, the claim
   that it happened rolls back with it — the trail cannot describe something
   that never landed, and cannot lose something that did.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import uuid
from collections.abc import Mapping, Sequence
from typing import Any, TypeVar, cast

from sqlalchemy import ColumnElement, Text
from sqlalchemy.orm import class_mapper

from app.core.exceptions import NotFoundError
from app.platform.audit.service import Action as AuditAction
from app.platform.audit.service import AuditService, audit_for_session
from app.products.crm.shared.pagination import PageParams
from app.products.crm.shared.repository import TenantOwnedModel, TenantScopedRepository
from app.products.crm.shared.visibility import RecordVisibility

ModelT = TypeVar("ModelT", bound=TenantOwnedModel)

#: Columns that carry no information about *what the user changed* — they are
#: bookkeeping the framework maintains — so they are left out of audit diffs.
#: ``updated_at``/``updated_by_id`` change on every single update and would
#: otherwise appear in every record, drowning the field that actually moved.
#:
#: ``search_vector`` (`P3-W20-BE-01`) is here for the same reason and one more.
#: It is *derived* — PostgreSQL recomputes it from columns already in the diff,
#: so recording it says nothing the trail does not already say, at the cost of
#: a page of lexemes per entry. It is also deferred, and the snapshot below
#: reads every column by name: touching a deferred attribute on a detached or
#: mid-flush instance triggers a lazy load, which under asyncio is a
#: ``MissingGreenlet`` rather than a query.
_AUDIT_IGNORED_COLUMNS = frozenset(
    {
        "id",
        "organization_id",
        "created_at",
        "updated_at",
        "created_by_id",
        "updated_by_id",
        "search_vector",
    }
)

#: Attributes tried, in order, when naming a record in the trail.
#:
#: ``email`` is last and is a genuine last resort — leads and contacts both
#: expose ``full_name``, so it is only reached by an entity with no name of any
#: kind. It is stored unmasked when it is reached, which is deliberate and the
#: same decision ``entity_label`` makes for a provisioned user: the label's one
#: job is to say *which record* this was, and a masked label cannot. The
#: address is masked wherever it appears in ``details`` (redaction.py).
_LABEL_ATTRIBUTES = ("name", "full_name", "subject", "title", "email")


class TenantScopedService[ModelT: TenantOwnedModel]:
    """CRUD over one CRM entity, always scoped to a single organization."""

    #: Human-readable name used in 404 messages.
    entity_name: str = "Record"

    def __init__(self, repository: TenantScopedRepository[ModelT], model: type[ModelT]) -> None:
        self._repository = repository
        self._model = model

    # --- Audit identity ----------------------------------------------------
    #
    # Both derived from what the module already declares rather than restated
    # per service, so a new CRM module is audited correctly the moment it
    # subclasses this — there is nothing extra to remember.

    @property
    def audit_module(self) -> str:
        """The permission module this entity belongs to, e.g. ``lead_sources``.

        The table name and the permission module name are the same string by
        construction (``authorization/catalog.PERMISSION_MODULES`` is written
        from the CRM folder names), which is what lets the trail be filtered by
        the same vocabulary the permission matrix uses.
        """
        return str(self._model.__tablename__)  # type: ignore[attr-defined]

    @property
    def audit_entity_type(self) -> str:
        """The record kind, e.g. ``LEAD_SOURCE``. Derived from ``entity_name``."""
        return self.entity_name.upper().replace(" ", "_")

    def audit_label(self, entity: ModelT) -> str | None:
        """A human-readable name for ``entity``, captured at write time.

        Stored on the record so the trail still reads sensibly once the row it
        refers to has been renamed or purged. Subclasses override when the
        obvious attribute is not the useful one.
        """
        for attribute in _LABEL_ATTRIBUTES:
            value = getattr(entity, attribute, None)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    @property
    def audit(self) -> AuditService:
        """Audit service bound to this entity's own session and transaction."""
        return audit_for_session(self._repository.session)

    # --- Reads -------------------------------------------------------------

    async def get_or_404(
        self,
        entity_id: uuid.UUID,
        organization_id: uuid.UUID,
        *,
        visibility: RecordVisibility | None = None,
    ) -> ModelT:
        """Fetch a record in the caller's organization, or raise 404.

        A record belonging to another tenant produces the same 404 as one that
        does not exist. Returning 403 instead would confirm the id is real and
        leak the existence of another tenant's data. A record the caller may
        not see for record-level reasons takes the same path, and for the same
        reason.

        Because every write path resolves its target through this method,
        passing ``visibility`` here also stops an edit or a delete reaching a
        record the caller cannot read — the rule is enforced once rather than
        re-stated per verb.
        """
        entity = await self._repository.get(
            entity_id,
            organization_id,
            visibility=self._visibility_filter(visibility),
        )
        if entity is None:
            raise NotFoundError(f"{self.entity_name} not found.")
        return entity

    async def list(
        self,
        organization_id: uuid.UUID,
        *,
        params: PageParams,
        filters: Sequence[ColumnElement[bool]] = (),
        visibility: RecordVisibility | None = None,
    ) -> tuple[Sequence[ModelT], int]:
        return await self._repository.list(
            organization_id,
            params=params,
            filters=filters,
            visibility=self._visibility_filter(visibility),
        )

    def _visibility_filter(
        self, visibility: RecordVisibility | None
    ) -> ColumnElement[bool] | None:
        """Translate a resolved visibility into a predicate, or nothing.

        ``None`` means the caller did not ask for record-level narrowing —
        reference-data modules and internal callers — and produces exactly the
        query that existed before this feature.
        """
        if visibility is None:
            return None
        return visibility.filter_for(self._model)

    async def record_export(
        self,
        *,
        organization_id: uuid.UUID,
        actor_id: uuid.UUID | None,
        row_count: int,
        filters_applied: Mapping[str, Any] | None = None,
    ) -> None:
        """Append the audit entry for a completed export (`P3-W22-BE-03`).

        Lives here, beside the CRUD audit calls, for the reason given at the
        top of this module: every entity service inherits it, so the next
        module to gain an export cannot ship one that records nothing.

        No row identifiers are stored. A ten-thousand-row export would write a
        ten-thousand-element array into a JSON column, and the question the
        trail has to answer is "who took how much of what, filtered how" --
        the rows themselves are still in the database to compare against.

        ``filters_applied`` passes through the audit module's redaction like
        every other ``details`` payload, so a filter value cannot smuggle a
        credential into the trail.
        """
        await self.audit.record(
            organization_id=organization_id,
            action=AuditAction.RECORDS_EXPORTED,
            module=self.audit_module,
            actor_id=actor_id,
            entity_type=self.audit_entity_type,
            details={
                "row_count": row_count,
                "filters": dict(filters_applied) if filters_applied else {},
            },
        )

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

        # Ownership defaults to whoever created the record, on any model that
        # has the column. Without this a rep creating a lead and not picking an
        # owner would produce an unowned row — and under record-level
        # visibility "unowned" means "visible to the whole organization", the
        # opposite of what creating your own lead should do.
        if hasattr(self._model, "owner_id") and payload.get("owner_id") is None:
            payload["owner_id"] = actor_id

        entity = self._model(  # type: ignore[call-arg]
            **payload,
            organization_id=organization_id,
            created_by_id=actor_id,
            updated_by_id=actor_id,
        )
        created = await self._repository.add(entity)

        await self.audit.record_change(
            organization_id=organization_id,
            action=AuditAction.CREATED,
            module=self.audit_module,
            entity_type=self.audit_entity_type,
            entity_id=cast("uuid.UUID", created.id),
            entity_label=self.audit_label(created),
            actor_id=actor_id,
            after=self._audit_snapshot(created),
        )
        return created

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

        The audit diff is taken over the fields the caller actually submitted,
        read immediately before and after the assignment. A PATCH that re-sends
        identical values therefore records nothing — see
        ``AuditService.record_change``.
        """
        touched = [field for field in values if field not in _AUDIT_IGNORED_COLUMNS]
        before = self._audit_snapshot(entity, fields=touched)

        for field, value in values.items():
            if field in {"organization_id", "id", "created_by_id", "created_at"}:
                continue
            setattr(entity, field, value)
        entity.updated_by_id = actor_id  # type: ignore[attr-defined]
        await self._repository.flush()

        await self.audit.record_change(
            organization_id=cast("uuid.UUID", entity.organization_id),
            action=AuditAction.UPDATED,
            module=self.audit_module,
            entity_type=self.audit_entity_type,
            entity_id=cast("uuid.UUID", entity.id),
            entity_label=self.audit_label(entity),
            actor_id=actor_id,
            before=before,
            after=self._audit_snapshot(entity, fields=touched),
        )
        return entity

    async def soft_delete(
        self, entity: ModelT, *, actor_id: uuid.UUID | None, at: dt.datetime | None = None
    ) -> ModelT:
        """Archive a record. Nothing is physically deleted through the API."""
        entity.updated_by_id = actor_id  # type: ignore[attr-defined]
        label = self.audit_label(entity)
        deleted = await self._repository.soft_delete(entity, at=at)

        await self.audit.record(
            organization_id=cast("uuid.UUID", deleted.organization_id),
            action=AuditAction.DELETED,
            module=self.audit_module,
            entity_type=self.audit_entity_type,
            entity_id=cast("uuid.UUID", deleted.id),
            entity_label=label,
            actor_id=actor_id,
            # Soft deletion, so the record is recoverable and the timestamp is
            # what an administrator needs in order to find and restore it.
            details={"deleted_at": deleted.deleted_at, "soft": True},
        )
        return deleted

    # --- Audit internals ---------------------------------------------------

    def _audit_snapshot(
        self, entity: ModelT, *, fields: Sequence[str] | None = None
    ) -> dict[str, Any]:
        """Column values of ``entity``, shaped for an audit diff.

        Two exclusions, both deliberate:

        * bookkeeping columns (:data:`_AUDIT_IGNORED_COLUMNS`) — they change on
          every write and say nothing about the user's intent;
        * ``Text`` column *contents* — a note body, a call description, a
          lead's free-form notes. Copying that prose into an append-only table
          would put a colleague's private note in front of every audit reader
          and keep it there permanently. ``String(n)`` columns are structured
          fields (names, statuses, addresses) and are recorded in full, subject
          to redaction.

        A ``Text`` column is summarised as its length plus a short digest
        rather than simply elided. The digest is what makes the *change* still
        auditable: two different bodies of the same length would otherwise
        compare equal and the edit would vanish from the trail entirely. It
        also lets an investigator confirm that a text they hold is the one that
        was stored, without the trail ever having stored it.

        Values still pass through ``redaction.redact`` afterwards, which is
        what strips credentials and masks contact details.
        """
        mapper = class_mapper(cast("type[Any]", self._model))
        wanted = set(fields) if fields is not None else None

        snapshot: dict[str, Any] = {}
        for attribute in mapper.column_attrs:
            key = attribute.key
            if key in _AUDIT_IGNORED_COLUMNS:
                continue
            if wanted is not None and key not in wanted:
                continue

            value = getattr(entity, key, None)
            column = attribute.columns[0]
            if isinstance(column.type, Text) and isinstance(value, str):
                snapshot[key] = _summarise_text(value)
            else:
                snapshot[key] = value
        return snapshot


def _summarise_text(value: str) -> str:
    """Describe a free-text value without reproducing it.

    ``sha256`` truncated to twelve hex characters: long enough that two edits
    are distinguishable in practice, and this is a change marker rather than a
    security boundary — nothing authorizes on it.
    """
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]
    return f"<text: {len(value)} chars, sha256:{digest}>"


__all__ = ["TenantScopedService"]
