"""Request and response contracts for CSV import."""

from __future__ import annotations

import enum

from pydantic import BaseModel, Field


class DuplicatePolicy(enum.StrEnum):
    """What to do with a row the entity's own rule calls a duplicate.

    The rule itself is decision C03, already implemented in each service: a
    duplicate is *warned about, not blocked*, and the caller re-submits with
    ``allow_duplicate``. This enum is how an importer expresses that choice
    once for a whole file instead of per row.

    There is deliberately no ``UPDATE`` option. Matching an incoming row to an
    existing record and overwriting it is a different feature with different
    failure modes -- a mis-mapped column silently rewriting live data being the
    obvious one -- and it is not what this round of UAT needs.
    """

    #: Leave the existing record alone and report the row as skipped.
    SKIP = "SKIP"
    #: Create the row anyway, exactly as ``allow_duplicate=true`` does.
    CREATE = "CREATE"


class ImportFieldInfo(BaseModel):
    """One column an importer can map a CSV header onto."""

    name: str
    required: bool


class ImportEntityInfo(BaseModel):
    """What the mapping step needs to render itself for one entity."""

    slug: str
    label: str
    fields: list[ImportFieldInfo]
    duplicate_field: str
    max_rows: int


class ImportRowIssue(BaseModel):
    """One thing wrong with one row.

    ``row`` is the line number in the uploaded file as a human counts them --
    the header is line 1, so the first data row is 2. Reporting the parser's
    zero-based index would make an importer hunt for the wrong line.
    """

    row: int
    field: str | None = Field(
        default=None, description="Column at fault, when the failure names one."
    )
    message: str


class ImportSummary(BaseModel):
    """The counts a person needs to decide whether the import went well."""

    total_rows: int
    created: int
    skipped_duplicates: int
    failed: int

    @property
    def has_failures(self) -> bool:
        return self.failed > 0


class ImportResult(BaseModel):
    """The outcome of a preview or a commit.

    The same shape for both, because they are the same execution -- one is
    rolled back. An importer comparing the preview to the final summary is
    comparing like with like, which is the point of a dry run.
    """

    #: ``True`` when nothing was kept. The wizard shows a confirm step for a
    #: preview and a completion step for a commit, and must not confuse them.
    dry_run: bool
    summary: ImportSummary
    #: Rows that could not be created, with the reason. Capped -- see the
    #: service. A file where every row is wrong does not need ten thousand
    #: identical messages to make the point.
    errors: list[ImportRowIssue]
    #: Rows the entity's duplicate rule matched, whether or not they were
    #: created. Reported separately from errors: a duplicate is a decision,
    #: not a mistake.
    duplicates: list[ImportRowIssue]
    #: Headers found in the file that were not mapped to a field. Surfaced so
    #: a mis-mapped column is visible rather than silently dropped.
    ignored_columns: list[str]


__all__ = [
    "DuplicatePolicy",
    "ImportEntityInfo",
    "ImportFieldInfo",
    "ImportResult",
    "ImportRowIssue",
    "ImportSummary",
]
