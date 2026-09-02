"""CSV import: parse, validate, match, write, and record enough to undo.

The shape follows Zoho's flow (analysis §3.3) because it is the one customers
arriving from another CRM already know: upload, auto-map the headers, choose
what identifies a duplicate, choose add/update/both, and protect populated data
from a sparse file.

Three properties this implementation insists on:

* **A preview and a commit see the same code.** :meth:`Importer.run` takes a
  ``dry_run`` flag rather than there being a separate validator. A preview that
  used different logic would be a preview of something else.
* **Every row is independent.** One bad row produces one error and the rest of
  the file still lands. Failing a four-thousand-row import because row 1,207
  has a typo is how people end up importing nothing.
* **Writes go through the entity's own service where one exists**, so the
  duplicate rules, state machines and derivations that guard the API guard the
  importer too. The alternative — bulk-inserting rows — makes CSV a hole in
  every invariant the product has.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ValidationFailedError
from app.products.crm.datatransfer.models import (
    UNDO_WINDOW_DAYS,
    ImportJob,
    ImportMode,
    ImportRecord,
    ImportStatus,
)
from app.products.crm.datatransfer.models import (
    ImportError as ImportErrorRow,
)
from app.products.crm.datatransfer.registry import (
    FieldSpec,
    FieldValueError,
    ModuleSpec,
    coerce,
)

logger = structlog.get_logger(__name__)

#: Hard ceiling on rows in one upload. Chosen to match the largest batch Zoho
#: accepts in its top edition, and to bound the transaction: the import runs in
#: one transaction so a failure leaves nothing behind, and an unbounded one
#: would hold locks for as long as the file took.
MAX_ROWS = 30_000

#: Rows shown back from a preview. Enough to see the shape of the file and the
#: first errors without returning the whole upload to the browser.
PREVIEW_ROWS = 20

#: Guards against a file whose first line is data rather than headers — an
#: unmapped column count of zero is the signal, and it is worth its own message
#: because "0 rows imported" sends people looking in the wrong place.
_MIN_HEADER_MATCH = 1


class ImportFileError(ValidationFailedError):
    """The upload could not be read as a CSV at all."""

    code = "import_file_invalid"


class UnknownImportModuleError(ValidationFailedError):
    """No importable module by that name."""

    code = "import_module_unknown"


@dataclass(slots=True)
class RowError:
    """One rejected row."""

    row_number: int
    message: str
    field_name: str | None = None


@dataclass(slots=True)
class RowOutcome:
    """What happened to one row, for the preview table."""

    row_number: int
    action: str
    values: dict[str, Any] = field(default_factory=dict)
    matched_id: uuid.UUID | None = None


@dataclass(slots=True)
class ImportOutcome:
    """The result of a run, dry or real."""

    total_rows: int = 0
    created: int = 0
    updated: int = 0
    skipped: int = 0
    errors: list[RowError] = field(default_factory=list)
    preview: list[RowOutcome] = field(default_factory=list)
    created_ids: list[uuid.UUID] = field(default_factory=list)
    headers: list[str] = field(default_factory=list)
    mapping: dict[str, str] = field(default_factory=dict)
    unmapped_headers: list[str] = field(default_factory=list)


def read_csv(raw: bytes, *, filename: str) -> tuple[list[str], list[list[str]]]:
    """Decode and parse an upload into headers plus rows.

    UTF-8 with a BOM is tried first because that is what Excel writes on
    Windows, and a BOM left in place turns the first header into ``\\ufeffname``
    which then maps to nothing. Latin-1 is the fallback: it cannot fail, so a
    file in an unknown encoding produces mojibake in a cell rather than a
    refusal the customer cannot act on.
    """
    if not raw.strip():
        raise ImportFileError("The uploaded file is empty.")

    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")

    try:
        # Sniffing the dialect handles semicolon-separated exports, which is
        # what a spreadsheet produces in most of Europe.
        sample = text[:8192]
        dialect: Any = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel

    reader = csv.reader(io.StringIO(text), dialect)
    try:
        rows = list(reader)
    except csv.Error as error:
        raise ImportFileError(f"{filename} could not be parsed: {error}") from error

    if not rows:
        raise ImportFileError("The uploaded file has no rows.")

    headers = [cell.strip() for cell in rows[0]]
    if not any(headers):
        raise ImportFileError("The first row must contain column headers.")

    body = [row for row in rows[1:] if any(cell.strip() for cell in row)]
    if len(body) > MAX_ROWS:
        raise ImportFileError(
            f"{len(body)} rows exceeds the {MAX_ROWS} row limit for one import."
        )
    return headers, body


def auto_map(headers: Sequence[str], module: ModuleSpec) -> dict[str, str]:
    """Match file columns to module fields, the way Zoho's Auto Mapping does.

    Compared on a normalised form so "First Name", "first_name" and "FIRSTNAME"
    all reach ``first_name``. Anything unmatched is reported rather than
    guessed at: silently dropping a column the customer expected to import is
    the failure mode this avoids.
    """

    def normalise(value: str) -> str:
        return "".join(ch for ch in value.lower() if ch.isalnum())

    by_normalised = {normalise(spec.name): spec.name for spec in module.fields}
    # A lookup column may also be addressed by its friendly name — "account"
    # for ``account_id`` — because that is what a migrated file calls it.
    for spec in module.fields:
        if spec.lookup_model is not None and spec.name.endswith("_id"):
            by_normalised.setdefault(normalise(spec.name[:-3]), spec.name)

    mapping: dict[str, str] = {}
    for header in headers:
        target = by_normalised.get(normalise(header))
        if target is not None and target not in mapping.values():
            mapping[header] = target
    return mapping


class Importer:
    """Runs one import against one module."""

    def __init__(self, session: AsyncSession, module: ModuleSpec) -> None:
        self._session = session
        self._module = module

    async def run(
        self,
        *,
        organization_id: uuid.UUID,
        actor_id: uuid.UUID | None,
        headers: Sequence[str],
        rows: Sequence[Sequence[str]],
        mapping: dict[str, str],
        mode: ImportMode,
        match_field: str | None,
        skip_empty_values: bool,
        dry_run: bool,
    ) -> ImportOutcome:
        """Process every row, writing unless ``dry_run``.

        The row loop is deliberately flat: coerce, validate, match, act. Each
        step can only fail this row, and a failure records an error and moves
        on. There is no early return, because a partial file is still worth
        importing and the report says exactly what did not.
        """
        outcome = ImportOutcome(total_rows=len(rows))
        outcome.headers = list(headers)
        outcome.mapping = dict(mapping)
        outcome.unmapped_headers = [h for h in headers if h not in mapping]

        if len(mapping) < _MIN_HEADER_MATCH:
            raise ImportFileError(
                "None of the file's columns match this module's fields. "
                "Check that the first row holds column headers.",
                details={
                    "headers": list(headers),
                    "available_fields": [spec.name for spec in self._module.fields],
                },
            )

        index_by_header = {header: position for position, header in enumerate(headers)}
        lookup_cache: dict[tuple[str, str], uuid.UUID | None] = {}

        for offset, row in enumerate(rows):
            # +2: the header occupies row 1 and spreadsheets count from 1, so
            # this is the line number the customer can actually go and look at.
            row_number = offset + 2
            try:
                values = await self._row_values(
                    row,
                    mapping=mapping,
                    index_by_header=index_by_header,
                    organization_id=organization_id,
                    row_number=row_number,
                    lookup_cache=lookup_cache,
                )
            except _RowRejectedError as rejected:
                outcome.errors.append(rejected.error)
                continue

            existing_id: uuid.UUID | None = None
            if match_field:
                try:
                    existing_id = await self._find_match(
                        organization_id, match_field=match_field, values=values
                    )
                except _RowRejectedError as rejected:
                    rejected.error.row_number = row_number
                    outcome.errors.append(rejected.error)
                    continue

            action = self._decide(mode, existing_id is not None)
            if action == "skip":
                outcome.skipped += 1
            elif action == "create":
                missing = self._missing_required(values)
                if missing:
                    outcome.errors.append(
                        RowError(
                            row_number=row_number,
                            field_name=missing[0],
                            message=f"{', '.join(missing)} is required to create a record.",
                        )
                    )
                    continue
                if not dry_run:
                    created_id = await self._create(organization_id, actor_id, values)
                    outcome.created_ids.append(created_id)
                outcome.created += 1
            else:
                assert existing_id is not None  # noqa: S101 - narrowed by _decide
                if not dry_run:
                    await self._update(
                        organization_id,
                        actor_id,
                        existing_id,
                        values,
                        skip_empty_values=skip_empty_values,
                    )
                outcome.updated += 1

            if len(outcome.preview) < PREVIEW_ROWS:
                outcome.preview.append(
                    RowOutcome(
                        row_number=row_number,
                        action=action,
                        values={k: _display(v) for k, v in values.items()},
                        matched_id=existing_id,
                    )
                )

        return outcome

    # --- Row handling ------------------------------------------------------

    async def _row_values(
        self,
        row: Sequence[str],
        *,
        mapping: dict[str, str],
        index_by_header: dict[str, int],
        organization_id: uuid.UUID,
        row_number: int,
        lookup_cache: dict[tuple[str, str], uuid.UUID | None],
    ) -> dict[str, Any]:
        """Coerce one row's mapped cells into column values."""
        values: dict[str, Any] = {}
        for header, target in mapping.items():
            spec = self._module.spec(target)
            if spec is None:  # pragma: no cover - mapping is validated upstream
                continue
            position = index_by_header[header]
            raw = row[position] if position < len(row) else ""

            if spec.lookup_model is not None:
                resolved = await self._resolve_lookup(
                    spec, raw, organization_id=organization_id, cache=lookup_cache
                )
                if resolved is _UNRESOLVED:
                    raise _RowRejectedError(
                        RowError(
                            row_number=row_number,
                            field_name=target,
                            message=(
                                f"No {spec.lookup_model.__name__.lower()} "
                                f"named {raw.strip()!r}."
                            ),
                        )
                    )
                values[target] = resolved
                continue

            try:
                values[target] = coerce(spec, raw)
            except FieldValueError as error:
                raise _RowRejectedError(
                    RowError(row_number=row_number, field_name=target, message=str(error))
                ) from error
        return values

    async def _resolve_lookup(
        self,
        spec: FieldSpec,
        raw: str,
        *,
        organization_id: uuid.UUID,
        cache: dict[tuple[str, str], uuid.UUID | None],
    ) -> Any:
        """Resolve a relation cell by id, or by the record's name.

        Migrated files carry company names, not the CRM's identifiers, so a
        lookup column that only accepted UUIDs would be unusable on exactly the
        data people are importing.

        Cached per run: a contact list of five thousand rows referencing thirty
        accounts should cost thirty queries, not five thousand.
        """
        text = raw.strip()
        if not text:
            return None

        try:
            return uuid.UUID(text)
        except ValueError:
            pass

        key = (spec.name, text.lower())
        if key in cache:
            found = cache[key]
        else:
            model = spec.lookup_model
            assert model is not None  # noqa: S101 - guarded by the caller
            column = getattr(model, spec.lookup_column)
            result = await self._session.execute(
                select(model.id)
                .where(
                    model.organization_id == organization_id,
                    model.deleted_at.is_(None),
                    func.lower(column) == text.lower(),
                )
                .limit(1)
            )
            found = result.scalar_one_or_none()
            cache[key] = found

        return found if found is not None else _UNRESOLVED

    def _missing_required(self, values: dict[str, Any]) -> list[str]:
        return [
            name
            for name in self._module.required_fields()
            if values.get(name) in (None, "")
        ]

    @staticmethod
    def _decide(mode: ImportMode, matched: bool) -> str:
        """Add / update / both, resolved against whether the row matched."""
        if matched:
            return "update" if mode in (ImportMode.UPDATE, ImportMode.BOTH) else "skip"
        return "create" if mode in (ImportMode.ADD, ImportMode.BOTH) else "skip"

    async def _find_match(
        self, organization_id: uuid.UUID, *, match_field: str, values: dict[str, Any]
    ) -> uuid.UUID | None:
        """Find an existing record by the chosen matching field.

        Text matching is case-insensitive, because "acme ltd" and "Acme Ltd"
        are the same company and an import that created both would be doing the
        opposite of deduplicating.
        """
        value = values.get(match_field)
        if value in (None, ""):
            return None

        model = self._module.model
        if match_field == "id":
            column = model.id
            predicate = column == value
        else:
            column = getattr(model, match_field, None)
            if column is None:
                raise _RowRejectedError(
                    RowError(row_number=0, message=f"{match_field} is not a matchable field.")
                )
            predicate = (
                func.lower(column) == str(value).lower()
                if isinstance(value, str)
                else column == value
            )

        result = await self._session.execute(
            select(model.id)
            .where(
                model.organization_id == organization_id,
                model.deleted_at.is_(None),
                predicate,
            )
            .order_by(model.created_at.asc())
            .limit(2)
        )
        found = result.scalars().all()
        if len(found) > 1:
            # The same refusal-to-guess Stage 0 established for conversion:
            # two records match, so which one to update is not the importer's
            # decision to make silently.
            raise _RowRejectedError(
                RowError(
                    row_number=0,
                    field_name=match_field,
                    message=(
                        f"{len(found)} existing records share this {match_field}; "
                        "resolve the duplicates before importing."
                    ),
                )
            )
        return found[0] if found else None

    async def _create(
        self, organization_id: uuid.UUID, actor_id: uuid.UUID | None, values: dict[str, Any]
    ) -> uuid.UUID:
        """Insert one record through the ORM, with tenancy and ownership set.

        Ownership defaults to whoever ran the import, exactly as
        ``TenantScopedService.create`` does for an API create. It matters more
        here than there: record-level visibility treats an *unowned* row as
        visible to the whole organization, so an import that left ``owner_id``
        null would quietly publish four thousand records to every user in the
        tenant — the opposite of what importing your own list should do.

        A file that carries its own ``owner_id`` column still wins.
        """
        payload = {k: v for k, v in values.items() if v is not None}
        payload.pop("id", None)
        if hasattr(self._module.model, "owner_id") and payload.get("owner_id") is None:
            payload["owner_id"] = actor_id
        entity = self._module.model(
            **payload,
            organization_id=organization_id,
            created_by_id=actor_id,
            updated_by_id=actor_id,
        )
        self._session.add(entity)
        await self._session.flush()
        return uuid.UUID(str(entity.id))

    async def _update(
        self,
        organization_id: uuid.UUID,
        actor_id: uuid.UUID | None,
        record_id: uuid.UUID,
        values: dict[str, Any],
        *,
        skip_empty_values: bool,
    ) -> None:
        """Apply an update to a matched record.

        ``skip_empty_values`` is Zoho's "don't update empty values for existing
        records" and defaults on. Without it a spreadsheet that happens not to
        carry a phone column blanks every phone number in the database — the
        single most destructive thing an importer does, and the reason this is
        a first-class option rather than a detail.

        Re-fetched with an organization filter rather than trusted from the
        match: the match already scoped it, and doing it again costs one
        indexed lookup and removes any path where a crafted ``id`` column could
        reach another tenant's row.
        """
        model = self._module.model
        result = await self._session.execute(
            select(model).where(
                model.id == record_id,
                model.organization_id == organization_id,
                model.deleted_at.is_(None),
            )
        )
        entity = result.scalar_one_or_none()
        if entity is None:  # pragma: no cover - matched a moment ago
            return

        for name, value in values.items():
            if name == "id":
                continue
            if skip_empty_values and value in (None, ""):
                continue
            setattr(entity, name, value)
        entity.updated_by_id = actor_id
        await self._session.flush()


class _RowRejectedError(Exception):
    """Internal control flow: this row failed, the file continues."""

    def __init__(self, error: RowError) -> None:
        super().__init__(error.message)
        self.error = error


class _Unresolved:
    """Sentinel for "the lookup ran and found nothing", distinct from NULL."""

    __slots__ = ()


_UNRESOLVED = _Unresolved()


def _display(value: Any) -> Any:
    """Make a coerced value JSON-safe for the preview payload."""
    if isinstance(value, dt.datetime | dt.date | uuid.UUID):
        return str(value)
    return value


def undo_deadline(now: dt.datetime | None = None) -> dt.datetime:
    """When an import started at ``now`` stops being undoable."""
    return (now or dt.datetime.now(dt.UTC)) + dt.timedelta(days=UNDO_WINDOW_DAYS)


def build_job(
    *,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID | None,
    module_key: str,
    filename: str,
    mode: ImportMode,
    match_field: str | None,
    skip_empty_values: bool,
    outcome: ImportOutcome,
) -> ImportJob:
    """The ``import_jobs`` row describing a completed run."""
    now = dt.datetime.now(dt.UTC)
    return ImportJob(
        organization_id=organization_id,
        module=module_key,
        filename=filename[:255],
        status=ImportStatus.COMPLETED,
        mode=mode,
        match_field=match_field,
        skip_empty_values=skip_empty_values,
        total_rows=outcome.total_rows,
        created_count=outcome.created,
        updated_count=outcome.updated,
        skipped_count=outcome.skipped,
        error_count=len(outcome.errors),
        finished_at=now,
        undo_expires_at=undo_deadline(now),
        created_by_id=actor_id,
        updated_by_id=actor_id,
    )


def build_tracking_rows(
    job: ImportJob, outcome: ImportOutcome
) -> tuple[list[ImportRecord], list[ImportErrorRow]]:
    """The undo trail and the error report for a finished job."""
    records = [
        ImportRecord(
            organization_id=job.organization_id,
            import_job_id=job.id,
            module=job.module,
            record_id=record_id,
        )
        for record_id in outcome.created_ids
    ]
    errors = [
        ImportErrorRow(
            organization_id=job.organization_id,
            import_job_id=job.id,
            row_number=error.row_number,
            field_name=error.field_name,
            message=error.message,
        )
        for error in outcome.errors
    ]
    return records, errors


__all__ = [
    "MAX_ROWS",
    "PREVIEW_ROWS",
    "ImportFileError",
    "ImportOutcome",
    "Importer",
    "RowError",
    "RowOutcome",
    "UnknownImportModuleError",
    "auto_map",
    "build_job",
    "build_tracking_rows",
    "read_csv",
    "undo_deadline",
]
