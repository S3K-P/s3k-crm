"""Automated RLS coverage audit over the live database schema.

:mod:`app.core.rls` *applies* tenant isolation; this module *verifies* it, and
it does so by reading PostgreSQL's catalogues rather than by trusting a list
someone maintained by hand.

That distinction is the whole point. A hardcoded roster of tenant-scoped tables
only ever proves the tables **on the list** are protected — the table someone
adds next week is absent from the list, so the audit stays green while an
unprotected table sits in production. Discovery is therefore inverted: ask the
database which tables exist, and require every one of them to be either

* tenant-scoped — carrying ``organization_id``, with RLS enabled, FORCEd, and a
  policy isolating on that column for reads *and* writes; or
* explicitly exempt — named in the caller's exemption map with a written reason.

A newly created table is neither until someone makes it one, so the audit fails
on it by default. Failing closed on the unknown case is what makes this a
control rather than a formality.

The checks are pure functions over catalogue rows (:func:`audit_tenant_isolation`),
kept separate from the queries that fetch them (:data:`TABLE_SECURITY_SQL`,
:data:`TABLE_POLICY_SQL`), so the same logic runs against a sync migration
connection, an async test engine, or synthetic rows in a unit test.

What this cannot see: whether a policy that *mentions* the tenant setting
actually compares it to the right thing. That half is proven behaviourally, by
reading and writing across organizations as an ordinary role — see
``tests/integration/test_crm_rls.py``.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final

from sqlalchemy import text
from sqlalchemy.sql.elements import TextClause

from app.core.models import TENANT_SETTING

__all__ = [
    "TABLE_POLICY_SQL",
    "TABLE_SECURITY_SQL",
    "TENANT_COLUMN",
    "Finding",
    "TablePolicy",
    "TableSecurity",
    "audit_tenant_isolation",
    "build_table_security",
    "format_findings",
]

#: The tenant discriminator supplied by ``TenantMixin``. A table carrying it is
#: holding customer data by definition, and must be isolated.
TENANT_COLUMN: Final = "organization_id"

#: ``pg_policy.polcmd`` codes; ``*`` is ``FOR ALL``.
_SELECT: Final = "r"
_INSERT: Final = "a"
_UPDATE: Final = "w"
_DELETE: Final = "d"
_ALL: Final = "*"

#: Every command a tenant policy set must cover. Policies protecting reads but
#: not DELETE would leave a tenant able to destroy another organization's rows.
_REQUIRED_COMMANDS: Final = frozenset({_SELECT, _INSERT, _UPDATE, _DELETE})

_COMMAND_NAMES: Final[dict[str, str]] = {
    _SELECT: "SELECT",
    _INSERT: "INSERT",
    _UPDATE: "UPDATE",
    _DELETE: "DELETE",
    _ALL: "ALL",
}

#: Ordinary and partitioned tables. Partitions are deliberately included: RLS on
#: a parent does not protect a partition addressed directly, so if partitioning
#: is ever introduced the audit should fail until someone decides what each
#: partition's policy is.
TABLE_SECURITY_SQL: Final[TextClause] = text(
    """
    SELECT c.relname                     AS table_name,
           (a.attname IS NOT NULL)       AS has_tenant_column,
           COALESCE(a.attnotnull, false) AS tenant_column_not_null,
           c.relrowsecurity              AS rls_enabled,
           c.relforcerowsecurity         AS rls_forced
      FROM pg_class c
      JOIN pg_namespace n ON n.oid = c.relnamespace
      LEFT JOIN pg_attribute a
             ON a.attrelid = c.oid
            AND a.attname = :column
            AND a.attnum > 0
            AND NOT a.attisdropped
     WHERE n.nspname = :schema
       AND c.relkind IN ('r', 'p')
     ORDER BY c.relname
    """
)

TABLE_POLICY_SQL: Final[TextClause] = text(
    """
    SELECT c.relname                               AS table_name,
           p.polname                               AS policy_name,
           p.polcmd::text                          AS command,
           p.polpermissive                         AS permissive,
           pg_get_expr(p.polqual, p.polrelid)      AS using_expression,
           pg_get_expr(p.polwithcheck, p.polrelid) AS check_expression
      FROM pg_policy p
      JOIN pg_class c ON c.oid = p.polrelid
      JOIN pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname = :schema
     ORDER BY c.relname, p.polname
    """
)


@dataclass(frozen=True, slots=True)
class TablePolicy:
    """One ``pg_policy`` row, with its expressions rendered back to SQL."""

    name: str
    command: str
    permissive: bool
    using_expression: str | None
    check_expression: str | None

    @property
    def command_name(self) -> str:
        return _COMMAND_NAMES.get(self.command, self.command)

    @property
    def read_expression(self) -> str | None:
        """The predicate deciding which existing rows this policy exposes.

        ``None`` for INSERT policies — PostgreSQL forbids ``USING`` on them.
        """
        return None if self.command == _INSERT else self.using_expression

    @property
    def write_expression(self) -> str | None:
        """The predicate deciding which new rows this policy admits.

        An omitted ``WITH CHECK`` on UPDATE or ALL is **not** a gap: PostgreSQL
        reuses the ``USING`` expression as the write check. Verified against
        PostgreSQL 18 rather than assumed — an audit that reported every
        ``FOR ALL ... USING`` policy as write-unsafe would flag all thirteen
        CRM tables and teach everyone to ignore it.
        """
        if self.command == _INSERT:
            return self.check_expression
        if self.command in (_UPDATE, _ALL):
            return (
                self.check_expression
                if self.check_expression is not None
                else self.using_expression
            )
        return None

    def _scopes(self, expression: str | None, column: str) -> bool:
        """Whether ``expression`` constrains rows to the current tenant.

        Matched on substrings rather than parsed: ``pg_get_expr`` output is
        normalised by PostgreSQL, so both the column name and the setting
        lookup appear verbatim in the predicate this codebase generates.
        """
        return expression is not None and column in expression and TENANT_SETTING in expression

    def isolates_reads(self, column: str) -> bool:
        return self._scopes(self.read_expression, column)

    def isolates_writes(self, column: str) -> bool:
        return self._scopes(self.write_expression, column)

    def leaks(self, column: str) -> tuple[str, ...]:
        """Which of the accesses this policy grants escape the tenant scope."""
        leaking: list[str] = []
        if self.read_expression is not None and not self.isolates_reads(column):
            leaking.append("reads")
        if self.write_expression is not None and not self.isolates_writes(column):
            leaking.append("writes")
        return tuple(leaking)

    def is_tenant_policy(self, column: str) -> bool:
        """Whether every access this policy grants is confined to one tenant."""
        grants_access = self.read_expression is not None or self.write_expression is not None
        return grants_access and not self.leaks(column)

    @property
    def covered_commands(self) -> frozenset[str]:
        return _REQUIRED_COMMANDS if self.command == _ALL else frozenset({self.command})


@dataclass(frozen=True, slots=True)
class TableSecurity:
    """The security posture of one table, as PostgreSQL reports it."""

    schema: str
    name: str
    has_tenant_column: bool
    tenant_column_not_null: bool
    rls_enabled: bool
    rls_forced: bool
    policies: tuple[TablePolicy, ...]

    @property
    def qualified_name(self) -> str:
        return f"{self.schema}.{self.name}"


@dataclass(frozen=True, slots=True)
class Finding:
    """One way a table falls short of the tenant-isolation contract."""

    table: str
    problem: str
    detail: str

    def __str__(self) -> str:
        return f"{self.table}: {self.detail}"


def build_table_security(
    schema: str,
    table_rows: Iterable[Mapping[Any, Any]],
    policy_rows: Iterable[Mapping[Any, Any]],
) -> tuple[TableSecurity, ...]:
    """Assemble :class:`TableSecurity` values from the two catalogue queries.

    Split from execution so callers may run the SQL synchronously or
    asynchronously; both hand the resulting ``.mappings()`` rows here.

    Rows are typed as ``Mapping[Any, Any]`` rather than ``Mapping[str, Any]``
    because SQLAlchemy's ``RowMapping`` is keyed by a union of label types, and
    ``Mapping`` is invariant in its key. Values are narrowed on the way into
    the dataclasses below, which is where the real contract lives.
    """
    by_table: dict[str, list[TablePolicy]] = {}
    for row in policy_rows:
        by_table.setdefault(str(row["table_name"]), []).append(
            TablePolicy(
                name=str(row["policy_name"]),
                command=str(row["command"]),
                permissive=bool(row["permissive"]),
                using_expression=row["using_expression"],
                check_expression=row["check_expression"],
            )
        )

    return tuple(
        TableSecurity(
            schema=schema,
            name=str(row["table_name"]),
            has_tenant_column=bool(row["has_tenant_column"]),
            tenant_column_not_null=bool(row["tenant_column_not_null"]),
            rls_enabled=bool(row["rls_enabled"]),
            rls_forced=bool(row["rls_forced"]),
            policies=tuple(by_table.get(str(row["table_name"]), ())),
        )
        for row in table_rows
    )


def _audit_tenant_scoped(table: TableSecurity, column: str) -> list[Finding]:
    """Checks that apply to a table carrying the tenant column."""
    findings: list[Finding] = []
    name = table.qualified_name

    if not table.tenant_column_not_null:
        findings.append(
            Finding(
                name,
                "tenant_column_nullable",
                f"{column} is nullable, so a NULL row would belong to no tenant "
                "and be reachable only by bypassing RLS",
            )
        )

    if not table.rls_enabled:
        findings.append(
            Finding(
                name,
                "rls_disabled",
                f"carries {column} but row-level security is not enabled, so every "
                "tenant can read and write every row",
            )
        )
        # Every policy check below would only restate this one.
        return findings

    if not table.rls_forced:
        findings.append(
            Finding(
                name,
                "rls_not_forced",
                "row-level security is enabled but not FORCEd, so the table owner "
                "— which the application usually is — bypasses every policy",
            )
        )

    tenant_policies = [p for p in table.policies if p.permissive and p.is_tenant_policy(column)]

    if tenant_policies:
        covered = frozenset[str]().union(*(p.covered_commands for p in tenant_policies))
        uncovered = _REQUIRED_COMMANDS - covered
        if uncovered:
            findings.append(
                Finding(
                    name,
                    "commands_not_covered",
                    "no tenant policy covers "
                    + ", ".join(sorted(_COMMAND_NAMES[c] for c in uncovered)),
                )
            )

    else:
        findings.append(
            Finding(
                name,
                "no_tenant_policy",
                f"has no permissive policy isolating on {column}",
            )
        )

    for policy in table.policies:
        leaking = policy.leaks(column) if policy.permissive else ()
        if leaking:
            findings.append(
                Finding(
                    name,
                    "unscoped_permissive_policy",
                    f'permissive policy "{policy.name}" ({policy.command_name}) does '
                    f"not scope {' and '.join(leaking)} to {column}. Permissive "
                    "policies are OR-ed together, so this one widens access past "
                    "any tenant policy beside it",
                )
            )

    return findings


def audit_tenant_isolation(
    tables: Iterable[TableSecurity],
    *,
    exemptions: Mapping[str, str],
    column: str = TENANT_COLUMN,
) -> tuple[Finding, ...]:
    """Return every way ``tables`` breaks the tenant-isolation contract.

    An empty result means the schema is clean.

    Args:
        tables: discovered tables, from :func:`build_table_security`.
        exemptions: unqualified table name -> the written reason it holds no
            tenant data. A table that is neither tenant-scoped nor listed here
            is reported; that is what makes a newly added table fail by default
            instead of passing unnoticed.
        column: the tenant discriminator column.
    """
    findings: list[Finding] = []
    discovered: set[str] = set()

    for table in tables:
        discovered.add(table.name)
        exemption = exemptions.get(table.name)

        if table.has_tenant_column:
            if exemption is not None:
                findings.append(
                    Finding(
                        table.qualified_name,
                        "stale_exemption",
                        f"is listed as RLS-exempt ({exemption}) but now carries "
                        f"{column}; drop the exemption and enable RLS on it",
                    )
                )
            findings.extend(_audit_tenant_scoped(table, column))
        elif exemption is None:
            findings.append(
                Finding(
                    table.qualified_name,
                    "unclassified_table",
                    f"has no {column} and no documented exemption. Either give it "
                    "the tenant mixin and enable RLS in its migration, or record "
                    "why it holds no tenant data",
                )
            )

    findings.extend(
        Finding(
            name,
            "stale_exemption",
            "is listed as RLS-exempt but no such table exists; drop the entry so "
            "the list keeps meaning something",
        )
        for name in sorted(set(exemptions) - discovered)
    )

    return tuple(findings)


def format_findings(findings: Sequence[Finding]) -> str:
    """Render findings as an assertion message, one per line."""
    return "\n".join(f"  - {finding}" for finding in findings)
