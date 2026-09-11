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

from app.core.exceptions import AppError, NotFoundError
from app.platform.audit.service import Action as AuditAction
from app.platform.audit.service import AuditService, audit_for_session
from app.products.crm.common import CrmEntityType
from app.products.crm.shared.custom_field_hook import (
    custom_field_defaults,
    resolve_custom_fields,
)
from app.products.crm.shared.pagination import PageParams
from app.products.crm.shared.repository import TenantOwnedModel, TenantScopedRepository
from app.products.crm.shared.schemas import BulkOperationFailure, BulkOperationResult
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

    #: Which ``CrmEntityType`` this service's records are, when they support
    #: tenant-defined fields (Phase E). ``None`` — the default — means the
    #: entity has none, and every custom-field code path below is skipped
    #: entirely, so a module that never opted in pays nothing for the feature.
    #:
    #: Set on a subclass and custom values are validated on every create and
    #: update of that entity, here, in the funnel every write already passes
    #: through. That placement is the guarantee: there is no per-module call to
    #: forget, and no way to add a write path that stores a custom value
    #: nothing checked.
    crm_entity_type: CrmEntityType | None = None

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
        sort_column: ColumnElement[Any] | None = None,
    ) -> tuple[Sequence[ModelT], int]:
        """One page of rows, plus the total matching count.

        ``sort_column`` overrides the ``sort_by`` name for the one case a name
        cannot express: ordering by a tenant-defined field. It is built from
        that field's definition by the caller, never from the request.
        """
        return await self._repository.list(
            organization_id,
            params=params,
            filters=filters,
            visibility=self._visibility_filter(visibility),
            sort_column=sort_column,
        )

    def _visibility_filter(self, visibility: RecordVisibility | None) -> ColumnElement[bool] | None:
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

        if self.crm_entity_type is not None:
            # Everything else the caller submitted, before the resolved
            # `custom_fields` document replaces the raw one below — a
            # published layout's conditional rules (Checkpoint 4) may read any
            # of these built-in values. Snapshotting `payload` here rather
            # than after is a documented, narrow limitation: a rule reading
            # `owner_id` would not yet see the create-defaulted value assigned
            # further down, since that default is applied to whoever actually
            # created the record and no real layout condition targets it.
            record_context = {k: v for k, v in payload.items() if k != "custom_fields"}
            payload["custom_fields"] = await self._resolve_custom_fields(
                organization_id=organization_id,
                submitted=payload.get("custom_fields"),
                existing=await custom_field_defaults(
                    self._repository.session,
                    organization_id=organization_id,
                    entity_type=self.crm_entity_type,
                ),
                creating=True,
                record_context=record_context,
            )

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
        values = dict(values)
        if self.crm_entity_type is not None and "custom_fields" in values:
            # The record's built-in values as this write will leave them: its
            # current columns, overridden by whatever this PATCH also touches
            # — so a rule reading, say, a status this same request is not
            # changing still sees it, and one reading a column this request
            # *is* changing sees the new value, not the stale one still on
            # `entity`. Custom fields are excluded on both sides: the
            # replacement document is what `_resolve_custom_fields` computes
            # right below, and a stale/raw copy of it here would be wrong the
            # moment either differs from the final answer.
            record_context = {
                **self._built_in_snapshot(entity),
                **{k: v for k, v in values.items() if k != "custom_fields"},
            }
            # Merged against what the record already holds, so a PATCH that
            # names one custom field does not erase the others — the same
            # partial-update semantics the built-in columns have.
            values["custom_fields"] = await self._resolve_custom_fields(
                organization_id=cast("uuid.UUID", entity.organization_id),
                submitted=values["custom_fields"],
                existing=dict(getattr(entity, "custom_fields", None) or {}),
                creating=False,
                record_context=record_context,
            )

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

    # --- Bulk writes (Checkpoint 4) -----------------------------------------
    #
    # Both loop the *single-record* path — ``update``/``soft_delete`` above —
    # rather than issuing one UPDATE/DELETE statement over the whole id list.
    # That costs N round trips instead of one, and it is the only way to keep
    # every guarantee the single-record path already makes: per-record
    # permission and visibility (a caller cannot bulk-edit a record their role
    # or ownership would not let them edit one at a time), full custom-field
    # validation, and one audit entry per record rather than a single entry
    # that cannot say which of fifty records actually changed. A field this
    # method could silently corrupt at scale — a status or stage governed by a
    # blueprint state machine — is refused by construction: callers pass
    # ``values`` built from each entity's own ``*Update`` schema, which already
    # excludes those columns (``LeadUpdate`` excludes ``status``,
    # ``OpportunityUpdate`` excludes ``stage_id``) in favour of the dedicated
    # transition endpoints, which know how to bulk-move records through a
    # blueprint one at a time — see e.g. ``LeadService.bulk_change_status``.

    async def bulk_update(
        self,
        ids: Sequence[uuid.UUID],
        organization_id: uuid.UUID,
        *,
        actor_id: uuid.UUID | None,
        values: dict[str, Any],
        visibility: RecordVisibility | None = None,
    ) -> BulkOperationResult:
        """Apply the same partial update to every id, independently.

        Never partial-silent: every id in ``ids`` ends up in exactly one of
        ``succeeded`` or ``failed`` (with a reason), and a record already
        outside the caller's visibility or permission fails with the same
        message :meth:`get_or_404` would give a single request — "not found",
        never a leaked "you may not edit this one".
        """
        succeeded: list[uuid.UUID] = []
        failed: list[BulkOperationFailure] = []
        for entity_id in ids:
            try:
                entity = await self.get_or_404(entity_id, organization_id, visibility=visibility)
                await self._bulk_update_one(entity, actor_id=actor_id, values=dict(values))
                succeeded.append(entity_id)
            except AppError as exc:
                failed.append(BulkOperationFailure(id=entity_id, reason=exc.message))
        return BulkOperationResult(succeeded=succeeded, failed=failed)

    async def _bulk_update_one(
        self, entity: ModelT, *, actor_id: uuid.UUID | None, values: dict[str, Any]
    ) -> ModelT:
        """The single-record write ``bulk_update`` applies to one id.

        A hook rather than a direct call to :meth:`update`, so a subclass
        whose real update path adds a rule beyond the generic one —
        ``OpportunityService.update_open`` refuses to patch a closed deal —
        can point bulk updates at it too. Without this, a bulk edit would
        silently reopen the one business rule its single-record PATCH already
        enforces.
        """
        return await self.update(entity, actor_id=actor_id, values=values)

    async def bulk_delete(
        self,
        ids: Sequence[uuid.UUID],
        organization_id: uuid.UUID,
        *,
        actor_id: uuid.UUID | None,
        visibility: RecordVisibility | None = None,
    ) -> BulkOperationResult:
        """Archive every id, independently. See :meth:`bulk_update`."""
        succeeded: list[uuid.UUID] = []
        failed: list[BulkOperationFailure] = []
        for entity_id in ids:
            try:
                entity = await self.get_or_404(entity_id, organization_id, visibility=visibility)
                await self.soft_delete(entity, actor_id=actor_id)
                succeeded.append(entity_id)
            except AppError as exc:
                failed.append(BulkOperationFailure(id=entity_id, reason=exc.message))
        return BulkOperationResult(succeeded=succeeded, failed=failed)

    # --- Custom fields -----------------------------------------------------

    async def _resolve_custom_fields(
        self,
        *,
        organization_id: uuid.UUID,
        submitted: Any,
        existing: Mapping[str, Any] | None,
        creating: bool,
        record_context: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Validate submitted custom values and return the document to store.

        Delegates through :mod:`~app.products.crm.shared.custom_field_hook`,
        which is what keeps this module free of an import it may not make. The
        assertion on ``crm_entity_type`` is for the type checker: both callers
        guard on it, and a subclass that reached here without one would be a
        programming error rather than a request the user could make.
        """
        entity_type = self.crm_entity_type
        assert entity_type is not None  # noqa: S101 - guarded by both callers
        return await resolve_custom_fields(
            self._repository.session,
            organization_id=organization_id,
            entity_type=entity_type,
            submitted=submitted if isinstance(submitted, Mapping) else None,
            existing=existing,
            creating=creating,
            record_context=record_context,
        )

    def _built_in_snapshot(self, entity: ModelT) -> dict[str, Any]:
        """``entity``'s current built-in column values, unmasked and unhashed.

        Unlike :meth:`_audit_snapshot`, a ``Text`` column is not summarised
        here — this feeds a Checkpoint 4 layout rule's *evaluation*, never a
        response body or a log, so there is no exposure to guard against, and
        summarising a description field to a hash would make a condition
        written against it (`"notes" contains "urgent"`) unable to ever match.
        """
        mapper = class_mapper(cast("type[Any]", self._model))
        return {
            attribute.key: getattr(entity, attribute.key, None)
            for attribute in mapper.column_attrs
            if attribute.key not in {"custom_fields", "search_vector"}
        }

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
