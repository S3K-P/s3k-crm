"""Import, export, undo and bulk operations over the registered CRM modules.

Everything here writes or reads across modules, so three rules apply without
exception:

* **Tenancy is never taken from the caller's payload.** Every statement filters
  on the ``organization_id`` of the authenticated principal.
* **Record-level visibility applies to reads.** An export is a read: a rep who
  cannot see a deal on screen must not be able to download it. The same
  :class:`RecordVisibility` predicate the list endpoints use is applied here,
  rather than a second implementation that could drift from it.
* **Bulk writes are audited as one event.** Fifty individual UPDATED entries
  describe fifty accidents; one BULK_UPDATED entry naming the field, the count
  and the ids describes a decision.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import uuid
from collections.abc import Sequence
from typing import Any, cast

import structlog
from sqlalchemy import ColumnElement, CursorResult, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationFailedError
from app.platform.audit.service import Action as AuditAction
from app.platform.audit.service import audit_for_session
from app.products.crm.datatransfer.importer import (
    Importer,
    ImportOutcome,
    auto_map,
    build_job,
    build_tracking_rows,
    read_csv,
)
from app.products.crm.datatransfer.models import (
    ImportError as ImportErrorRow,
)
from app.products.crm.datatransfer.models import (
    ImportJob,
    ImportMode,
    ImportRecord,
    ImportStatus,
)
from app.products.crm.datatransfer.registry import (
    MODULES,
    ModuleSpec,
    coerce,
    format_for_export,
    get_module,
)
from app.products.crm.shared.visibility import RecordVisibility

logger = structlog.get_logger(__name__)

#: Ceiling on ids accepted by one bulk call. Bounds the transaction and the
#: audit payload; a larger selection is a filter, not a list of ids.
MAX_BULK_IDS = 500

#: Ceiling on rows one export streams. High enough to be a real migration path,
#: low enough that a single request cannot exhaust memory building the file.
MAX_EXPORT_ROWS = 50_000


class UnknownModuleError(ValidationFailedError):
    """No CRM module is registered under that key."""

    code = "unknown_module"


class ImportNotUndoableError(ValidationFailedError):
    """The undo window has closed, or the import was already undone."""

    code = "import_not_undoable"


class BulkSelectionError(ValidationFailedError):
    """The selection is empty or larger than one call may carry."""

    code = "bulk_selection_invalid"


def require_module(key: str) -> ModuleSpec:
    module = get_module(key)
    if module is None:
        raise UnknownModuleError(
            f"{key!r} is not a CRM module that supports this operation.",
            details={"available": sorted(MODULES)},
        )
    return module


class DataTransferService:
    """Bulk data movement for one organization."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @property
    def _audit(self) -> Any:
        return audit_for_session(self._session)

    # --- Import ------------------------------------------------------------

    async def preview_import(
        self,
        *,
        organization_id: uuid.UUID,
        module_key: str,
        raw: bytes,
        filename: str,
        mapping: dict[str, str] | None,
        mode: ImportMode,
        match_field: str | None,
        skip_empty_values: bool,
    ) -> tuple[ModuleSpec, ImportOutcome]:
        """Validate an upload without writing anything.

        Runs the identical code path a real import runs, with ``dry_run`` set —
        a preview produced by different logic would be a preview of a different
        import. The session is rolled back to a savepoint afterwards so the
        lookups it performed leave nothing behind.
        """
        module = require_module(module_key)
        headers, rows = read_csv(raw, filename=filename)
        resolved_mapping = mapping or auto_map(headers, module)

        outcome = await Importer(self._session, module).run(
            organization_id=organization_id,
            actor_id=None,
            headers=headers,
            rows=rows,
            mapping=resolved_mapping,
            mode=mode,
            match_field=match_field,
            skip_empty_values=skip_empty_values,
            dry_run=True,
        )
        return module, outcome

    async def run_import(
        self,
        *,
        organization_id: uuid.UUID,
        actor_id: uuid.UUID | None,
        module_key: str,
        raw: bytes,
        filename: str,
        mapping: dict[str, str] | None,
        mode: ImportMode,
        match_field: str | None,
        skip_empty_values: bool,
    ) -> tuple[ImportJob, ImportOutcome]:
        """Import a file and record everything needed to undo it.

        The whole run is one transaction, so a failure part-way through leaves
        no half-imported file behind. Individual *row* failures are not
        failures of the run — they are recorded and the rest continues.
        """
        module = require_module(module_key)
        headers, rows = read_csv(raw, filename=filename)
        resolved_mapping = mapping or auto_map(headers, module)

        outcome = await Importer(self._session, module).run(
            organization_id=organization_id,
            actor_id=actor_id,
            headers=headers,
            rows=rows,
            mapping=resolved_mapping,
            mode=mode,
            match_field=match_field,
            skip_empty_values=skip_empty_values,
            dry_run=False,
        )

        job = build_job(
            organization_id=organization_id,
            actor_id=actor_id,
            module_key=module.key,
            filename=filename,
            mode=mode,
            match_field=match_field,
            skip_empty_values=skip_empty_values,
            outcome=outcome,
        )
        self._session.add(job)
        await self._session.flush()

        records, errors = build_tracking_rows(job, outcome)
        self._session.add_all(records)
        self._session.add_all(errors)
        await self._session.flush()

        logger.info(
            "import_completed",
            organization_id=str(organization_id),
            module=module.key,
            created=outcome.created,
            updated=outcome.updated,
            skipped=outcome.skipped,
            errors=len(outcome.errors),
        )
        await self._audit.record(
            organization_id=organization_id,
            action=AuditAction.IMPORTED,
            module=module.key,
            actor_id=actor_id,
            entity_type="IMPORT_JOB",
            entity_id=job.id,
            entity_label=job.filename,
            details={
                "mode": mode.value,
                "match_field": match_field,
                "created": outcome.created,
                "updated": outcome.updated,
                "skipped": outcome.skipped,
                "errors": len(outcome.errors),
            },
        )
        return job, outcome

    async def list_jobs(
        self, organization_id: uuid.UUID, *, limit: int = 50
    ) -> Sequence[ImportJob]:
        result = await self._session.execute(
            select(ImportJob)
            .where(
                ImportJob.organization_id == organization_id,
                ImportJob.deleted_at.is_(None),
            )
            .order_by(ImportJob.created_at.desc())
            .limit(limit)
        )
        return result.scalars().all()

    async def get_job(self, job_id: uuid.UUID, organization_id: uuid.UUID) -> ImportJob:
        result = await self._session.execute(
            select(ImportJob).where(
                ImportJob.id == job_id,
                ImportJob.organization_id == organization_id,
                ImportJob.deleted_at.is_(None),
            )
        )
        job = result.scalar_one_or_none()
        if job is None:
            raise NotFoundError("Import not found.")
        return job

    async def job_errors(
        self, job: ImportJob, *, limit: int = 200
    ) -> Sequence[ImportErrorRow]:
        result = await self._session.execute(
            select(ImportErrorRow)
            .where(
                ImportErrorRow.import_job_id == job.id,
                ImportErrorRow.organization_id == job.organization_id,
            )
            .order_by(ImportErrorRow.row_number)
            .limit(limit)
        )
        return result.scalars().all()

    async def undo_import(
        self, job: ImportJob, *, actor_id: uuid.UUID | None
    ) -> int:
        """Remove the records this import created, and nothing else.

        **Only creations are reversed.** Records the import *updated* existed
        beforehand and stay, because reversing an update needs a before-image
        this deliberately does not store (see ``ImportRecord``). The endpoint
        says so, and the audit entry records both numbers, so nobody has to
        infer what an undo did.

        Soft-deleted rather than physically removed, for the same reason every
        other delete in the product is: an undo that turns out to be the
        mistake must itself be recoverable.
        """
        if not job.is_undoable:
            raise ImportNotUndoableError(
                "This import can no longer be undone.",
                details={
                    "status": job.status.value,
                    "undone_at": job.undone_at.isoformat() if job.undone_at else None,
                    "undo_expires_at": (
                        job.undo_expires_at.isoformat() if job.undo_expires_at else None
                    ),
                },
            )

        module = require_module(job.module)
        result = await self._session.execute(
            select(ImportRecord.record_id).where(
                ImportRecord.import_job_id == job.id,
                ImportRecord.organization_id == job.organization_id,
            )
        )
        record_ids = list(result.scalars().all())

        removed = 0
        if record_ids:
            model = module.model
            now = dt.datetime.now(dt.UTC)
            # A single UPDATE rather than a row-by-row loop, still filtered on
            # the organization so a tampered tracking row could not reach
            # another tenant's data.
            update_result = await self._session.execute(
                model.__table__.update()
                .where(
                    model.id.in_(record_ids),
                    model.organization_id == job.organization_id,
                    model.deleted_at.is_(None),
                )
                .values(deleted_at=now, updated_by_id=actor_id)
            )
            removed = int(cast("CursorResult[Any]", update_result).rowcount or 0)

        job.status = ImportStatus.UNDONE
        job.undone_at = dt.datetime.now(dt.UTC)
        job.updated_by_id = actor_id
        await self._session.flush()

        logger.info(
            "import_undone",
            import_job_id=str(job.id),
            organization_id=str(job.organization_id),
            archived=removed,
        )
        await self._audit.record(
            organization_id=job.organization_id,
            action=AuditAction.IMPORT_UNDONE,
            module=job.module,
            actor_id=actor_id,
            entity_type="IMPORT_JOB",
            entity_id=job.id,
            entity_label=job.filename,
            details={
                "archived": removed,
                "tracked": len(record_ids),
                # Stated explicitly so the trail cannot be read as "the import
                # was fully reversed" when updates were left in place.
                "updates_not_reverted": job.updated_count,
            },
        )
        return removed

    # --- Export ------------------------------------------------------------

    async def export_csv(
        self,
        *,
        organization_id: uuid.UUID,
        module_key: str,
        visibility: RecordVisibility | None,
        filters: Sequence[ColumnElement[bool]] = (),
        limit: int = MAX_EXPORT_ROWS,
    ) -> tuple[ModuleSpec, str, int]:
        """Render the caller's visible rows as CSV.

        Visibility is applied in the query, not after: building the whole set
        and trimming it would mean the database had already handed this process
        rows the caller may not read.
        """
        module = require_module(module_key)
        model = module.model
        columns = module.exportable_fields()

        statement = select(model).where(
            model.organization_id == organization_id,
            model.deleted_at.is_(None),
        )
        for condition in filters:
            statement = statement.where(condition)
        if visibility is not None:
            predicate = visibility.filter_for(model)
            if predicate is not None:
                statement = statement.where(predicate)

        result = await self._session.execute(
            statement.order_by(model.created_at.desc()).limit(limit)
        )
        rows = result.scalars().all()

        buffer = io.StringIO()
        # QUOTE_MINIMAL with the default dialect: Excel-compatible, and the
        # quoting rules match what `read_csv` sniffs, so an export round-trips
        # back through the importer.
        writer = csv.writer(buffer, lineterminator="\n")
        writer.writerow(["id", *columns])
        for entity in rows:
            writer.writerow(
                [
                    str(entity.id),
                    *(format_for_export(getattr(entity, name, None)) for name in columns),
                ]
            )
        return module, buffer.getvalue(), len(rows)

    # --- Bulk operations ---------------------------------------------------

    def _validate_selection(self, ids: Sequence[uuid.UUID]) -> list[uuid.UUID]:
        unique = list(dict.fromkeys(ids))
        if not unique:
            raise BulkSelectionError("Select at least one record.")
        if len(unique) > MAX_BULK_IDS:
            raise BulkSelectionError(
                f"Select at most {MAX_BULK_IDS} records in one operation.",
                details={"selected": len(unique), "limit": MAX_BULK_IDS},
            )
        return unique

    async def _visible_ids(
        self,
        module: ModuleSpec,
        organization_id: uuid.UUID,
        ids: Sequence[uuid.UUID],
        *,
        visibility: RecordVisibility | None,
        include_deleted: bool = False,
    ) -> list[uuid.UUID]:
        """Narrow a selection to the rows this caller may actually act on.

        Everything a bulk endpoint does starts here. An id the caller cannot
        see is dropped silently rather than refused, for the same reason
        ``get_or_404`` returns 404 on another tenant's record: telling them
        which of their guesses were real is itself a leak.
        """
        model = module.model
        statement = select(model.id).where(
            model.organization_id == organization_id,
            model.id.in_(list(ids)),
        )
        if not include_deleted:
            statement = statement.where(model.deleted_at.is_(None))
        else:
            statement = statement.where(model.deleted_at.is_not(None))
        if visibility is not None:
            predicate = visibility.filter_for(model)
            if predicate is not None:
                statement = statement.where(predicate)
        result = await self._session.execute(statement)
        return [uuid.UUID(str(value)) for value in result.scalars().all()]

    async def bulk_update(
        self,
        *,
        organization_id: uuid.UUID,
        actor_id: uuid.UUID | None,
        module_key: str,
        ids: Sequence[uuid.UUID],
        values: dict[str, str],
        visibility: RecordVisibility | None,
    ) -> int:
        """Set the same fields on many records.

        Only fields the registry marks ``bulk_updatable`` are accepted. That
        list is narrower than the importable one on purpose: mass-editing a
        status or an owner is the point of the feature, and mass-editing a name
        or an email address is a mistake nobody meant to make at scale.
        """
        module = require_module(module_key)
        selection = self._validate_selection(ids)

        coerced: dict[str, Any] = {}
        for name, raw in values.items():
            if name not in module.bulk_updatable:
                raise ValidationFailedError(
                    f"{name!r} cannot be set in bulk.",
                    details={"updatable": sorted(module.bulk_updatable)},
                )
            spec = module.spec(name)
            if spec is None:  # pragma: no cover - bulk_updatable names are fields
                continue
            coerced[name] = coerce(spec, raw)

        if not coerced:
            raise ValidationFailedError("No fields to update.")

        visible = await self._visible_ids(
            module, organization_id, selection, visibility=visibility
        )
        if not visible:
            return 0

        model = module.model
        result = await self._session.execute(
            model.__table__.update()
            .where(model.id.in_(visible), model.organization_id == organization_id)
            .values(**coerced, updated_by_id=actor_id)
        )
        changed = int(cast("CursorResult[Any]", result).rowcount or 0)
        await self._session.flush()

        await self._audit.record(
            organization_id=organization_id,
            action=AuditAction.BULK_UPDATED,
            module=module.permission_module,
            actor_id=actor_id,
            entity_type=module.key.upper(),
            entity_id=None,
            entity_label=f"{changed} {module.key}",
            details={
                "fields": {k: format_for_export(v) for k, v in coerced.items()},
                "count": changed,
                "requested": len(selection),
                "ids": [str(value) for value in visible],
            },
        )
        return changed

    async def bulk_archive(
        self,
        *,
        organization_id: uuid.UUID,
        actor_id: uuid.UUID | None,
        module_key: str,
        ids: Sequence[uuid.UUID],
        visibility: RecordVisibility | None,
    ) -> int:
        """Soft-delete many records."""
        return await self._set_deleted(
            organization_id=organization_id,
            actor_id=actor_id,
            module_key=module_key,
            ids=ids,
            visibility=visibility,
            archive=True,
        )

    async def bulk_restore(
        self,
        *,
        organization_id: uuid.UUID,
        actor_id: uuid.UUID | None,
        module_key: str,
        ids: Sequence[uuid.UUID],
        visibility: RecordVisibility | None,
    ) -> int:
        """Bring archived records back.

        The counterpart the product was missing: soft delete without restore is
        not a safety net, it is rows accumulating (analysis §5.6).
        """
        return await self._set_deleted(
            organization_id=organization_id,
            actor_id=actor_id,
            module_key=module_key,
            ids=ids,
            visibility=visibility,
            archive=False,
        )

    async def _set_deleted(
        self,
        *,
        organization_id: uuid.UUID,
        actor_id: uuid.UUID | None,
        module_key: str,
        ids: Sequence[uuid.UUID],
        visibility: RecordVisibility | None,
        archive: bool,
    ) -> int:
        module = require_module(module_key)
        selection = self._validate_selection(ids)
        visible = await self._visible_ids(
            module,
            organization_id,
            selection,
            visibility=visibility,
            include_deleted=not archive,
        )
        if not visible:
            return 0

        model = module.model
        result = await self._session.execute(
            model.__table__.update()
            .where(model.id.in_(visible), model.organization_id == organization_id)
            .values(
                deleted_at=dt.datetime.now(dt.UTC) if archive else None,
                updated_by_id=actor_id,
            )
        )
        changed = int(cast("CursorResult[Any]", result).rowcount or 0)
        await self._session.flush()

        await self._audit.record(
            organization_id=organization_id,
            action=AuditAction.BULK_ARCHIVED if archive else AuditAction.BULK_RESTORED,
            module=module.permission_module,
            actor_id=actor_id,
            entity_type=module.key.upper(),
            entity_id=None,
            entity_label=f"{changed} {module.key}",
            details={"count": changed, "ids": [str(value) for value in visible]},
        )
        return changed

    async def bulk_assign_owner(
        self,
        *,
        organization_id: uuid.UUID,
        actor_id: uuid.UUID | None,
        module_key: str,
        ids: Sequence[uuid.UUID],
        owner_id: uuid.UUID | None,
        visibility: RecordVisibility | None,
    ) -> int:
        """Reassign many records to one owner.

        Its own endpoint rather than a bulk update of ``owner_id`` because
        ownership decides record-level visibility (ADR-010): reassigning is an
        access-control change, and it earns an audit action of its own so it is
        findable without reading field diffs.
        """
        module = require_module(module_key)
        if not hasattr(module.model, "owner_id"):
            raise ValidationFailedError(f"{module.key} records have no owner.")

        selection = self._validate_selection(ids)
        visible = await self._visible_ids(
            module, organization_id, selection, visibility=visibility
        )
        if not visible:
            return 0

        model = module.model
        result = await self._session.execute(
            model.__table__.update()
            .where(model.id.in_(visible), model.organization_id == organization_id)
            .values(owner_id=owner_id, updated_by_id=actor_id)
        )
        changed = int(cast("CursorResult[Any]", result).rowcount or 0)
        await self._session.flush()

        await self._audit.record(
            organization_id=organization_id,
            action=AuditAction.OWNER_REASSIGNED,
            module=module.permission_module,
            actor_id=actor_id,
            entity_type=module.key.upper(),
            entity_id=None,
            entity_label=f"{changed} {module.key}",
            details={
                "to": str(owner_id) if owner_id else None,
                "count": changed,
                "ids": [str(value) for value in visible],
            },
        )
        return changed

    async def count_module(
        self, module_key: str, organization_id: uuid.UUID
    ) -> int:
        """Live row count, used by the export UI to warn before a large file."""
        module = require_module(module_key)
        model = module.model
        result = await self._session.execute(
            select(func.count())
            .select_from(model)
            .where(
                model.organization_id == organization_id,
                model.deleted_at.is_(None),
            )
        )
        return int(result.scalar_one())

    async def purge_expired_tracking(self, *, older_than: dt.datetime) -> int:
        """Drop undo trails for imports past their window.

        Called by the retention job. The ``import_jobs`` rows stay — the
        history of what was imported is worth keeping — but the per-record
        tracking behind them is only useful while undo is possible, and it is
        by far the larger table.
        """
        result = await self._session.execute(
            delete(ImportRecord).where(
                ImportRecord.import_job_id.in_(
                    select(ImportJob.id).where(
                        ImportJob.undo_expires_at.is_not(None),
                        ImportJob.undo_expires_at < older_than,
                    )
                )
            )
        )
        return int(cast("CursorResult[Any]", result).rowcount or 0)


__all__ = [
    "MAX_BULK_IDS",
    "MAX_EXPORT_ROWS",
    "BulkSelectionError",
    "DataTransferService",
    "ImportNotUndoableError",
    "UnknownModuleError",
    "require_module",
]
