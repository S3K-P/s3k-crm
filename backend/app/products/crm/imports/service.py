"""Parse, validate and load a CSV into a CRM entity.

The shape of the thing: one function, :meth:`ImportService.run`, executes the
whole file and is told whether to keep the result. ``preview`` passes
``dry_run=True`` and the SAVEPOINT is discarded; ``commit`` passes ``False``.
Both take the identical path, so a preview cannot promise something the commit
then does differently.

Per-row isolation is the other half. Each row is written inside its own nested
SAVEPOINT, so a row that violates a constraint rolls back to just before
itself and the file continues. Without that, one bad row aborts the enclosing
transaction and every later row fails with ``InFailedSQLTransaction`` -- which
looks exactly like "the whole file was invalid" and is the classic way a
partial-failure report becomes a lie.
"""

from __future__ import annotations

import csv
import io
import uuid
from collections.abc import Mapping, Sequence
from typing import Any

import structlog
from fastapi import status as http_status
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError, ConflictError
from app.platform.audit.service import Action as AuditAction
from app.platform.audit.service import audit_for_session
from app.products.crm.imports.catalog import ImportableEntity
from app.products.crm.imports.schemas import (
    DuplicatePolicy,
    ImportResult,
    ImportRowIssue,
    ImportSummary,
)

logger = structlog.get_logger(__name__)

#: Hard ceiling on one upload.
#:
#: Stated in the UI and enforced here. The import is synchronous -- it runs
#: inside the request, holding a transaction -- so the ceiling is what stops a
#: large file becoming a timeout that leaves an importer guessing how much
#: landed. `P3-W23-BE-02`'s batch worker is what lifts it, and is out of scope
#: for this round.
MAX_IMPORT_ROWS = 5_000

#: Bytes accepted before the file is rejected unread. 5 000 rows of a CRM
#: entity is comfortably under this; anything larger is either not a CRM export
#: or is over the row cap anyway, and both are better refused before being
#: parsed into memory.
MAX_IMPORT_BYTES = 8 * 1024 * 1024

#: Issues of each kind returned to the caller. A file where every row is wrong
#: makes its point in the first fifty; sending ten thousand identical messages
#: helps nobody and is a denial-of-service against the importer's browser.
MAX_REPORTED_ISSUES = 50


class ImportFileError(AppError):
    """The upload could not be read as a CSV at all."""

    status_code = http_status.HTTP_422_UNPROCESSABLE_CONTENT
    code = "import_file_invalid"
    message = "The uploaded file could not be read as CSV."


class ImportTooLargeError(AppError):
    """The upload exceeds the row or byte ceiling."""

    status_code = http_status.HTTP_413_CONTENT_TOO_LARGE
    code = "import_too_large"
    message = (
        f"An import is limited to {MAX_IMPORT_ROWS:,} rows. "
        "Split the file and import it in parts."
    )


def parse_csv(raw: bytes) -> tuple[list[str], list[dict[str, str]]]:
    """Read an uploaded file into headers and row dictionaries.

    Decoded as UTF-8 with a BOM tolerated, because the file a tester is most
    likely to re-upload is one this application exported, and Excel writes a
    BOM back out. ``utf-8-sig`` strips it when present and is plain UTF-8 when
    it is not.

    Raises:
        ImportFileError: the bytes are not decodable text, or carry no header.
        ImportTooLargeError: more than :data:`MAX_IMPORT_ROWS` data rows.
    """
    if len(raw) > MAX_IMPORT_BYTES:
        raise ImportTooLargeError

    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ImportFileError(
            "The file is not valid UTF-8 text. Re-save it as CSV UTF-8 and try again."
        ) from exc

    # A NUL byte means a binary file (or a UTF-16 export) reached us with a
    # .csv name. csv.reader would produce plausible-looking garbage from it.
    if "\x00" in text:
        raise ImportFileError("The file looks binary rather than CSV.")

    reader = csv.reader(io.StringIO(text))
    try:
        headers = next(reader)
    except StopIteration:
        raise ImportFileError("The file is empty.") from None

    headers = [header.strip() for header in headers]
    if not any(headers):
        raise ImportFileError("The first line must be a header row naming the columns.")

    rows: list[dict[str, str]] = []
    for values in reader:
        if not any(value.strip() for value in values):
            continue  # a trailing blank line is not a row
        if len(rows) >= MAX_IMPORT_ROWS:
            raise ImportTooLargeError
        rows.append(dict(zip(headers, values, strict=False)))

    return headers, rows


class ImportService:
    """Loads mapped CSV rows into one CRM entity."""

    def __init__(self, session: AsyncSession, entity: ImportableEntity) -> None:
        self._session = session
        self._entity = entity

    async def run(
        self,
        *,
        organization_id: uuid.UUID,
        actor_id: uuid.UUID | None,
        headers: Sequence[str],
        rows: Sequence[Mapping[str, str]],
        mapping: Mapping[str, str],
        duplicate_policy: DuplicatePolicy,
        dry_run: bool,
    ) -> ImportResult:
        """Execute the import, keeping it only when ``dry_run`` is false.

        Args:
            mapping: CSV header -> entity field. Headers absent from it are
                ignored and reported, so a column nobody mapped is visible
                rather than silently discarded.
            duplicate_policy: how the entity's own duplicate rule is answered.
            dry_run: when true, everything written here is rolled back before
                returning -- including the audit rows the creates produced.
        """
        create = self._entity.create(self._session)
        errors: list[ImportRowIssue] = []
        duplicates: list[ImportRowIssue] = []
        created = 0
        skipped = 0

        ignored = [header for header in headers if header and header not in mapping]

        # One SAVEPOINT around the whole run. Releasing it keeps the work;
        # rolling it back is the dry run, and takes the audit entries with it.
        outer = await self._session.begin_nested()
        try:
            for index, row in enumerate(rows):
                # +2: the header is line 1 and the reader is 0-based, so this
                # is the line number the importer sees in their spreadsheet.
                line = index + 2
                values = self._map_row(row, mapping)

                try:
                    payload = self._entity.schema.model_validate(values)
                except ValidationError as exc:
                    self._record_validation_errors(errors, exc, line=line)
                    continue

                outcome = await self._create_one(
                    create,
                    payload=payload,
                    organization_id=organization_id,
                    actor_id=actor_id,
                    duplicate_policy=duplicate_policy,
                    line=line,
                    errors=errors,
                    duplicates=duplicates,
                )
                if outcome == "created":
                    created += 1
                elif outcome == "skipped":
                    skipped += 1

            summary = ImportSummary(
                total_rows=len(rows),
                created=created,
                skipped_duplicates=skipped,
                failed=len(rows) - created - skipped,
            )

            if not dry_run:
                await self._record_audit(
                    organization_id=organization_id, actor_id=actor_id, summary=summary
                )
                await outer.commit()
            else:
                await outer.rollback()
        except Exception:
            if outer.is_active:
                await outer.rollback()
            raise

        return ImportResult(
            dry_run=dry_run,
            summary=summary,
            errors=errors[:MAX_REPORTED_ISSUES],
            duplicates=duplicates[:MAX_REPORTED_ISSUES],
            ignored_columns=ignored,
        )

    # --- Internals ---------------------------------------------------------

    def _map_row(
        self, row: Mapping[str, str], mapping: Mapping[str, str]
    ) -> dict[str, Any]:
        """Turn one CSV row into a candidate payload for the entity schema.

        Blank cells become ``None`` rather than ``""``. A spreadsheet has no
        way to express "absent", and an empty string would fail the schema's
        length or format rules on every optional column an importer left
        blank -- which would read as the file being wrong when it is not.

        Only mapped headers are read. Nothing here can set ``id`` or
        ``organization_id``: neither is on any ``*Create`` schema, and the
        shared service strips them regardless.
        """
        values: dict[str, Any] = {}
        for header, field in mapping.items():
            raw = row.get(header)
            if raw is None:
                continue
            trimmed = raw.strip()
            values[field] = trimmed if trimmed else None
        return values

    @staticmethod
    def _record_validation_errors(
        errors: list[ImportRowIssue], exc: ValidationError, *, line: int
    ) -> None:
        """Translate Pydantic's report into per-row, per-column messages.

        Kept at field granularity because that is what an importer fixes: "row
        14, email: not a valid email address" points at a cell, where "row 14
        failed" points at a line and leaves them reading it.
        """
        for error in exc.errors():
            location = error.get("loc") or ()
            field = str(location[0]) if location else None
            errors.append(
                ImportRowIssue(row=line, field=field, message=str(error.get("msg", "Invalid")))
            )

    async def _create_one(
        self,
        create: Any,
        *,
        payload: Any,
        organization_id: uuid.UUID,
        actor_id: uuid.UUID | None,
        duplicate_policy: DuplicatePolicy,
        line: int,
        errors: list[ImportRowIssue],
        duplicates: list[ImportRowIssue],
    ) -> str:
        """Create one record, in its own SAVEPOINT. Returns the outcome.

        The nested savepoint is what makes partial failure honest: a row that
        trips a database constraint rolls back to just before itself, and the
        rows after it still run. Sharing the enclosing transaction would leave
        it aborted, and every subsequent row would fail for a reason that has
        nothing to do with its contents.
        """
        values = payload.model_dump(exclude_unset=False)

        try:
            async with self._session.begin_nested():
                await create(
                    organization_id=organization_id,
                    actor_id=actor_id,
                    values=values,
                    allow_duplicate=duplicate_policy is DuplicatePolicy.CREATE,
                )
        except ConflictError as exc:
            # The entity's own duplicate rule fired (decision C03). Which field
            # it keys on is the entity's business; this only reports it.
            duplicates.append(
                ImportRowIssue(row=line, field=self._entity.duplicate_field, message=exc.message)
            )
            if duplicate_policy is DuplicatePolicy.SKIP:
                return "skipped"
            return "failed"
        except AppError as exc:
            # A business rule the entity enforces -- an account that does not
            # exist, a stage that is closed. Reported with its own message
            # rather than flattened to "invalid row".
            errors.append(ImportRowIssue(row=line, message=exc.message))
            return "failed"
        except Exception as exc:
            logger.warning("import_row_failed", line=line, error_type=type(exc).__name__)
            errors.append(
                ImportRowIssue(row=line, message="This row could not be saved.")
            )
            return "failed"

        return "created"

    async def _record_audit(
        self,
        *,
        organization_id: uuid.UUID,
        actor_id: uuid.UUID | None,
        summary: ImportSummary,
    ) -> None:
        """One entry for the file, not one per row.

        Each created record is already audited individually by the entity's own
        service. This entry answers the different question an auditor asks
        about a bulk load: who ran it, against what, and what happened to it.
        """
        await audit_for_session(self._session).record(
            organization_id=organization_id,
            action=AuditAction.RECORDS_IMPORTED,
            module=self._entity.module,
            actor_id=actor_id,
            entity_type=self._entity.label.upper().replace(" ", "_"),
            details={
                "total_rows": summary.total_rows,
                "created": summary.created,
                "skipped_duplicates": summary.skipped_duplicates,
                "failed": summary.failed,
            },
        )


__all__ = [
    "MAX_IMPORT_BYTES",
    "MAX_IMPORT_ROWS",
    "ImportFileError",
    "ImportService",
    "ImportTooLargeError",
    "parse_csv",
]
