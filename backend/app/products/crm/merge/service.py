"""Merging duplicate records (Phase F).

The dangerous operation in the product: the one place two records deliberately
become one, and the one whose mistakes are invisible until somebody goes
looking for history that is not there. The whole design is arranged so that
cannot happen.

**Nothing is lost.** Every reference to a losing record is moved to the
survivor before the loser is retired — its activities, tasks, notes, mail,
attachments, campaign memberships and every foreign key that named it. The
losers are soft-deleted, as everything in this product is, and each keeps a
``merged_into_id`` pointing at the survivor, so an old bookmark, an
integration's stored id, or an audit entry from last year still resolves to the
record the data now lives on.

**It is one transaction.** Every statement below runs on the request's session,
which commits once at the end. A failure halfway through leaves nothing moved
and nothing retired — the alternative, a record whose activities have been
reassigned but which is still live, is a duplicate pair that is now *worse*
than before anybody touched it.

**Concurrency.** The survivor and every loser are locked ``FOR UPDATE`` before
anything is read for the merge. Two people merging overlapping sets at the same
moment is rare and entirely plausible — two admins working the same duplicate
report — and without the lock the second merge would read a record the first is
about to retire and move references onto a row that is gone by the time it
commits. With it, the second waits and then fails cleanly on a record that is
no longer live.

**Permissions.** Merging requires ``EDIT`` *and* ``DELETE`` on the record's
module, checked in the router. It changes one record and retires others, and a
role granted only the first must not gain the second by routing through here.
Every record is resolved through the module's own visibility, so a merge cannot
reach a record the caller could not open — including, and especially, one
belonging to another tenant.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Mapping, Sequence
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import class_mapper

from app.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from app.platform.audit.service import Action as AuditAction
from app.platform.audit.service import audit_for_session
from app.platform.auth.dependencies import Principal
from app.products.crm.merge.catalog import (
    MAX_MERGE_RECORDS,
    MergeTarget,
)
from app.products.crm.shared.visibility import RecordVisibility

#: Where a field's surviving value came from.
#:
#: ``"primary"`` or a losing record's id. Deliberately not "the non-empty one":
#: a merge that guessed would sometimes be right and would give no way to say
#: which record's phone number is the current one, which is the single question
#: a merge screen exists to ask.
PRIMARY = "primary"


class MergeTargetsOverlapError(ValidationFailedError):
    code = "merge_targets_overlap"
    message = "The surviving record cannot also be one of the duplicates."


class TooManyMergeRecordsError(ValidationFailedError):
    code = "too_many_merge_records"
    message = f"At most {MAX_MERGE_RECORDS} records may be merged at once."


class RecordAlreadyMergedError(ConflictError):
    code = "record_already_merged"
    message = "One of these records has already been merged into another."


class MergeService:
    """Combines duplicates of one record type into a survivor."""

    def __init__(self, session: AsyncSession, target: MergeTarget) -> None:
        self._session = session
        self._target = target

    # --- Preview -----------------------------------------------------------

    async def preview(
        self, principal: Principal, *, primary_id: uuid.UUID, duplicate_ids: Sequence[uuid.UUID]
    ) -> dict[str, Any]:
        """What a merge would change, without changing anything.

        Answers the question the confirmation screen asks: which fields differ,
        and what would each become. Read-only and unlocked — a preview that
        took row locks would let anyone freeze a record by opening a dialog.
        The values it reports can therefore be stale by the time the merge
        runs, which is exactly why the merge re-reads under a lock rather than
        trusting anything decided here.
        """
        primary, duplicates = await self._resolve(
            principal, primary_id, duplicate_ids, lock=False
        )
        records = [primary, *duplicates]

        conflicts: list[dict[str, Any]] = []
        for name in self._mergeable_fields():
            values = {str(record.id): getattr(record, name, None) for record in records}
            distinct = {_comparable(value) for value in values.values() if not _is_blank(value)}
            if len(distinct) > 1:
                conflicts.append(
                    {
                        "field": name,
                        "values": values,
                        # What happens if the caller chooses nothing. Reported
                        # rather than left implicit, so the screen can show the
                        # outcome of pressing Merge without touching anything.
                        "default": _comparable(getattr(primary, name, None)),
                    }
                )

        return {
            "primary_id": primary.id,
            "duplicate_ids": [record.id for record in duplicates],
            "conflicts": conflicts,
            "related_counts": await self._related_counts(
                primary.organization_id, [record.id for record in duplicates]
            ),
        }

    # --- Merge -------------------------------------------------------------

    async def merge(
        self,
        principal: Principal,
        *,
        primary_id: uuid.UUID,
        duplicate_ids: Sequence[uuid.UUID],
        field_choices: Mapping[str, str] | None = None,
    ) -> Any:
        """Merge ``duplicate_ids`` into ``primary_id`` and return the survivor.

        Args:
            principal: the caller. Every record is resolved through their own
                visibility, so a merge cannot reach one they could not open.
            primary_id: the record that survives.
            duplicate_ids: the records retired into it.
            field_choices: ``{field: "primary" | "<duplicate id>"}``. Anything
                unmentioned keeps the survivor's value — except where the
                survivor's is blank and exactly one loser has a value, which is
                filled in. That fallback is the one piece of guessing here and
                it is the safe direction: it can only add information the
                merged record would otherwise have lost, and it never
                overwrites anything.

        Raises:
            NotFoundError: an id is unknown, another tenant's, or outside the
                caller's visibility — all indistinguishable, deliberately.
            MergeTargetsOverlapError: the survivor is also listed as a
                duplicate.
            RecordAlreadyMergedError: one of them is already merged away.
        """
        primary, duplicates = await self._resolve(
            principal, primary_id, duplicate_ids, lock=True
        )
        organization_id = primary.organization_id
        loser_ids = [record.id for record in duplicates]

        before = self._snapshot(primary)
        applied = self._apply_field_choices(primary, duplicates, field_choices or {})
        self._merge_custom_fields(primary, duplicates)
        primary.updated_by_id = principal.user_id

        moved = await self._repoint(organization_id, loser_ids, primary.id)

        now = dt.datetime.now(dt.UTC)
        for record in duplicates:
            record.merged_into_id = primary.id
            record.updated_by_id = principal.user_id
            record.deleted_at = now

        await self._session.flush()

        # One audit entry, on the survivor, in the same transaction as the
        # change it describes. On the survivor rather than one per loser
        # because "what happened to this record" is the question an
        # investigation asks, and the losing ids are in the payload.
        await audit_for_session(self._session).record(
            organization_id=organization_id,
            action=AuditAction.UPDATED,
            module=self._target.module,
            entity_type=self._target.noun.upper(),
            entity_id=primary.id,
            entity_label=_label(primary),
            actor_id=principal.user_id,
            details={
                "operation": "merge",
                "merged_ids": [str(record_id) for record_id in loser_ids],
                "merged_labels": [_label(record) for record in duplicates],
                "fields_taken_from_duplicate": applied,
                "before": before,
                "after": self._snapshot(primary),
                "references_moved": moved,
            },
        )
        return primary

    # --- Resolution --------------------------------------------------------

    async def _resolve(
        self,
        principal: Principal,
        primary_id: uuid.UUID,
        duplicate_ids: Sequence[uuid.UUID],
        *,
        lock: bool,
    ) -> tuple[Any, list[Any]]:
        """Fetch the survivor and the losers, or raise.

        One query for all of them rather than one each: they are the same
        table, the same tenant and the same visibility, and asking per id would
        be an N+1 on the operation with the most reason to be careful. It also
        means the ``FOR UPDATE`` takes every lock in one statement, in a
        deterministic order, which is what stops two concurrent merges
        deadlocking against each other.
        """
        unique_duplicates = list(dict.fromkeys(duplicate_ids))
        if not unique_duplicates:
            raise ValidationFailedError("Choose at least one duplicate to merge.")
        if primary_id in unique_duplicates:
            raise MergeTargetsOverlapError
        if len(unique_duplicates) + 1 > MAX_MERGE_RECORDS:
            raise TooManyMergeRecordsError

        model = self._target.model
        wanted = [primary_id, *unique_duplicates]
        visibility = RecordVisibility.for_module(principal, self._target.module)

        statement = select(model).where(
            model.organization_id == principal.organization_id,
            model.deleted_at.is_(None),
            model.id.in_(wanted),
        )
        predicate = visibility.filter_for(model)
        if predicate is not None:
            statement = statement.where(predicate)
        if lock:
            # Ordered by id so concurrent merges over overlapping sets take
            # their locks in the same sequence and queue instead of deadlocking.
            statement = statement.order_by(model.id.asc()).with_for_update()

        found = {record.id: record for record in (await self._session.execute(statement)).scalars()}

        missing = [record_id for record_id in wanted if record_id not in found]
        if missing:
            # One message for "does not exist", "another tenant's" and "outside
            # your visibility". Distinguishing them would confirm the existence
            # of a record the caller may not see.
            raise NotFoundError(
                f"{self._target.noun.capitalize()} not found.",
                details={"ids": [str(record_id) for record_id in missing]},
            )
        if any(getattr(record, "merged_into_id", None) is not None for record in found.values()):
            raise RecordAlreadyMergedError

        return found[primary_id], [found[record_id] for record_id in unique_duplicates]

    # --- Field resolution --------------------------------------------------

    def _mergeable_fields(self) -> list[str]:
        """Columns a caller may choose a value for.

        Derived from the mapper minus the target's protected set, so a column
        added to the model is mergeable by default and a column that must never
        move has to be named — the safe direction for a new field on a record.
        """
        mapper = class_mapper(self._target.model)
        return [
            attribute.key
            for attribute in mapper.column_attrs
            if attribute.key not in self._target.protected_fields
        ]

    def _apply_field_choices(
        self,
        primary: Any,
        duplicates: Sequence[Any],
        choices: Mapping[str, str],
    ) -> dict[str, str]:
        """Write the winning value into the survivor. Returns what moved.

        Two rules, in order:

        1. An explicit choice wins. ``"primary"`` keeps the survivor's value —
           including when that value is blank, which is a real answer: "this
           duplicate's phone number is wrong, drop it".
        2. Otherwise, a blank on the survivor is filled from a loser when
           exactly one has a value. *Exactly* one: with two different values and
           no instruction there is no non-arbitrary winner, and picking the
           first would make the outcome depend on the order the ids arrived in.
        """
        taken: dict[str, str] = {}
        by_id = {str(record.id): record for record in duplicates}

        for name in self._mergeable_fields():
            chosen = choices.get(name)
            if chosen is not None and chosen != PRIMARY:
                source = by_id.get(chosen)
                if source is None:
                    raise ValidationFailedError(
                        f"'{chosen}' is not one of the duplicates being merged.",
                        details={"field": name},
                    )
                setattr(primary, name, getattr(source, name, None))
                taken[name] = chosen
                continue
            if chosen == PRIMARY:
                continue

            if _is_blank(getattr(primary, name, None)):
                candidates = {
                    str(record.id): getattr(record, name)
                    for record in duplicates
                    if not _is_blank(getattr(record, name, None))
                }
                distinct = {_comparable(value) for value in candidates.values()}
                if len(distinct) == 1:
                    record_id, value = next(iter(candidates.items()))
                    setattr(primary, name, value)
                    taken[name] = record_id

        return taken

    def _merge_custom_fields(self, primary: Any, duplicates: Sequence[Any]) -> None:
        """Fill the survivor's blank custom values from the duplicates.

        Not offered as per-field choices, deliberately. Custom fields are
        tenant data, so a merge screen cannot enumerate them at build time, and
        the safe rule is the same one the built-in fields fall back to: never
        overwrite a value the survivor holds, only fill what it does not.

        The document is *replaced* rather than mutated, because JSONB is an
        opaque scalar to SQLAlchemy's change detection and an in-place update
        is silently not persisted.
        """
        if not hasattr(primary, "custom_fields"):
            return
        merged = dict(primary.custom_fields or {})
        for record in duplicates:
            for key, value in (getattr(record, "custom_fields", None) or {}).items():
                if _is_blank(merged.get(key)) and not _is_blank(value):
                    merged[key] = value
        primary.custom_fields = merged

    # --- Reference moving --------------------------------------------------

    async def _repoint(
        self,
        organization_id: uuid.UUID,
        loser_ids: Sequence[uuid.UUID],
        survivor_id: uuid.UUID,
    ) -> dict[str, int]:
        """Move everything that pointed at a loser onto the survivor.

        Bulk UPDATEs rather than loading rows: a busy account can have
        thousands of activities, and a merge must not depend on how many.
        Every statement carries ``organization_id`` even though the ids were
        already resolved inside the tenant — defence in depth, and the same
        rule every other query in the product follows.

        ``synchronize_session=False`` because nothing here is read back into
        Python afterwards; the rows are moved and the request is done with them.

        Returns a per-table count for the audit entry, which is what tells an
        investigator afterwards that a merge did move the history it claimed to.
        """
        moved: dict[str, int] = {}

        for reference in self._target.foreign_references:
            column = getattr(reference.model, reference.column)
            result = await self._session.execute(
                update(reference.model)
                .where(
                    reference.model.organization_id == organization_id,
                    column.in_(list(loser_ids)),
                )
                .values({reference.column: survivor_id})
                .execution_options(synchronize_session=False)
            )
            rows = _rows_affected(result)
            if rows:
                moved[reference.label] = rows

        for link in self._target.polymorphic_references:
            type_column = getattr(link.model, link.type_column)
            id_column = getattr(link.model, link.id_column)
            result = await self._session.execute(
                update(link.model)
                .where(
                    link.model.organization_id == organization_id,
                    type_column == link.type_value,
                    id_column.in_(list(loser_ids)),
                )
                .values({link.id_column: survivor_id})
                .execution_options(synchronize_session=False)
            )
            rows = _rows_affected(result)
            if rows:
                moved[link.label] = rows

        moved.update(
            await self._repoint_attachments(organization_id, loser_ids, survivor_id)
        )
        return moved

    async def _repoint_attachments(
        self,
        organization_id: uuid.UUID,
        loser_ids: Sequence[uuid.UUID],
        survivor_id: uuid.UUID,
    ) -> dict[str, int]:
        """Move files hanging off the losers.

        Written as SQL rather than through the documents module's ORM model:
        ``app.products`` may not import ``app.platform.*.models``
        (ARCHITECTURE-BOUNDARIES.md rule 2), and the documents *service* has no
        bulk-repoint operation to call — adding one would put a CRM-shaped
        concern into a Platform module, which the same rule forbids from the
        other direction.

        So this is the narrow exception, and it is kept narrow deliberately: one
        statement, parameterised throughout, tenant-scoped, touching one column.
        A file's storage object is not moved or copied — only the row that says
        which record it belongs to.
        """
        from sqlalchemy import text

        result = await self._session.execute(
            text(
                "UPDATE platform.attachments SET entity_id = :survivor "
                "WHERE organization_id = :organization_id "
                "  AND entity_type = :entity_type "
                "  AND entity_id = ANY(:loser_ids)"
            ),
            {
                "survivor": survivor_id,
                "organization_id": organization_id,
                "entity_type": self._target.entity_type.value,
                "loser_ids": list(loser_ids),
            },
        )
        rows = _rows_affected(result)
        return {"attachments": rows} if rows else {}

    async def _related_counts(
        self, organization_id: uuid.UUID, loser_ids: Sequence[uuid.UUID]
    ) -> dict[str, int]:
        """How much would move, for the confirmation screen.

        The same references the merge would repoint, counted rather than
        updated, so the screen can say "12 activities and 3 notes will move to
        the surviving record" instead of asking someone to take it on trust.
        """
        from sqlalchemy import func

        counts: dict[str, int] = {}
        for reference in self._target.foreign_references:
            column = getattr(reference.model, reference.column)
            total = await self._session.scalar(
                select(func.count())
                .select_from(reference.model)
                .where(
                    reference.model.organization_id == organization_id,
                    column.in_(list(loser_ids)),
                )
            )
            if total:
                counts[reference.label] = int(total)

        for link in self._target.polymorphic_references:
            total = await self._session.scalar(
                select(func.count())
                .select_from(link.model)
                .where(
                    link.model.organization_id == organization_id,
                    getattr(link.model, link.type_column) == link.type_value,
                    getattr(link.model, link.id_column).in_(list(loser_ids)),
                )
            )
            if total:
                counts[link.label] = int(total)

        return counts

    # --- Audit helpers -----------------------------------------------------

    def _snapshot(self, record: Any) -> dict[str, Any]:
        """The mergeable columns of ``record``, for the audit diff.

        Only the columns a merge can change, so the entry says what the merge
        did rather than restating the whole row. Values pass through the audit
        module's redaction like every other ``details`` payload.
        """
        return {name: _comparable(getattr(record, name, None)) for name in self._mergeable_fields()}


def _rows_affected(result: Any) -> int:
    """How many rows an UPDATE touched.

    ``rowcount`` is on ``CursorResult`` rather than the ``Result`` base that
    ``execute`` is declared to return, so it is read through a narrowing helper
    instead of an ``ignore`` comment at each of the five call sites. The value
    only ever feeds the audit entry's counts, so a driver that could not report
    it would understate the trail rather than break the merge.
    """
    return int(getattr(result, "rowcount", 0) or 0)


def _is_blank(value: Any) -> bool:
    """Whether a field holds nothing a person would call a value.

    ``0`` and ``False`` are values, not blanks — a truthiness test here would
    let a merge overwrite a zero deal size or a "no" flag with a duplicate's
    value, which is a silent data change nobody asked for.
    """
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    return isinstance(value, list | dict | tuple | set) and not value


def _comparable(value: Any) -> Any:
    """A JSON-safe form of a column value, for comparison and for the trail."""
    if isinstance(value, uuid.UUID | dt.datetime | dt.date):
        return str(value)
    if hasattr(value, "value") and isinstance(getattr(value, "value", None), str):
        return value.value  # a StrEnum member
    if isinstance(value, list | tuple | set):
        return [_comparable(item) for item in value]
    if isinstance(value, dict):
        return {key: _comparable(item) for key, item in value.items()}
    if isinstance(value, int | float | bool | str) or value is None:
        return value
    return str(value)


def _label(record: Any) -> str | None:
    """A human-readable name for a record, for the audit entry."""
    for attribute in ("name", "full_name", "email"):
        value = getattr(record, attribute, None)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


__all__ = [
    "PRIMARY",
    "MergeService",
    "MergeTargetsOverlapError",
    "RecordAlreadyMergedError",
    "TooManyMergeRecordsError",
]
