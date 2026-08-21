"""The RLS audit's own logic, exercised without a database.

``tests/integration/test_crm_rls.py`` points this audit at the real schema and
expects a clean result. A clean result is only meaningful if the audit can go
dirty, so every check gets a case here that makes it fire — otherwise a bug
that silently returns "no findings" would read as "the schema is perfect".

Synthetic catalogue rows rather than real ones on purpose: several of these
states (RLS enabled without FORCE, a permissive ``USING (true)`` policy beside
the tenant policy) are ones the migrations cannot produce, and pinning them
here is cheaper than manufacturing them in Postgres.
"""

from __future__ import annotations

import pytest

from app.core.models import TENANT_SETTING
from app.core.schema_audit import (
    TENANT_COLUMN,
    TableSecurity,
    audit_tenant_isolation,
    build_table_security,
    format_findings,
)
from app.products.crm.common import RLS_EXEMPT_TABLES

#: What ``enable_rls`` actually writes, as PostgreSQL renders it back.
TENANT_PREDICATE = (
    f"(organization_id = (NULLIF(current_setting('{TENANT_SETTING}'::text, true), "
    "''::text))::uuid)"
)

NO_EXEMPTIONS: dict[str, str] = {}


def _policy(
    *,
    name: str = "probe_tenant_isolation",
    command: str = "*",
    permissive: bool = True,
    using: str | None = TENANT_PREDICATE,
    check: str | None = TENANT_PREDICATE,
) -> dict[str, object]:
    """A ``pg_policy`` row shaped as the audit query returns it."""
    return {
        "table_name": "probe",
        "policy_name": name,
        "command": command,
        "permissive": permissive,
        "using_expression": using,
        "check_expression": check,
    }


def _table(
    *,
    name: str = "probe",
    has_tenant_column: bool = True,
    tenant_column_not_null: bool = True,
    rls_enabled: bool = True,
    rls_forced: bool = True,
) -> dict[str, object]:
    """A table row shaped as the audit query returns it."""
    return {
        "table_name": name,
        "has_tenant_column": has_tenant_column,
        "tenant_column_not_null": tenant_column_not_null,
        "rls_enabled": rls_enabled,
        "rls_forced": rls_forced,
    }


def _audit(
    table: dict[str, object],
    policies: list[dict[str, object]] | None = None,
    *,
    exemptions: dict[str, str] | None = None,
) -> set[str]:
    """Audit one synthetic table and return the problems reported for it."""
    discovered = build_table_security(
        "crm", [table], [] if policies is None else policies
    )
    findings = audit_tenant_isolation(
        discovered, exemptions=NO_EXEMPTIONS if exemptions is None else exemptions
    )
    return {finding.problem for finding in findings}


# --- The healthy case -------------------------------------------------------


def test_a_correctly_protected_tenant_table_produces_no_findings() -> None:
    """Guards the guard: if this failed, every case below would pass vacuously."""
    assert _audit(_table(), [_policy()]) == set()


def test_a_documented_exemption_without_the_tenant_column_passes() -> None:
    assert (
        _audit(
            _table(has_tenant_column=False, tenant_column_not_null=False, rls_enabled=False,
                   rls_forced=False),
            exemptions={"probe": "a reason someone wrote down"},
        )
        == set()
    )


# --- Tables carrying organization_id ----------------------------------------


def test_a_tenant_table_without_rls_is_reported() -> None:
    """The case the whole audit exists for."""
    assert "rls_disabled" in _audit(_table(rls_enabled=False, rls_forced=False))


def test_a_tenant_table_with_rls_enabled_but_not_forced_is_reported() -> None:
    """Without FORCE the owning role — usually the application — ignores policies."""
    assert "rls_not_forced" in _audit(_table(rls_forced=False), [_policy()])


def test_a_tenant_table_with_rls_but_no_policy_is_reported() -> None:
    assert "no_tenant_policy" in _audit(_table(), [])


def test_a_policy_that_ignores_the_tenant_column_is_not_counted_as_isolation() -> None:
    unscoped = _policy(name="probe_all", using="true", check="true")

    problems = _audit(_table(), [unscoped])

    assert "no_tenant_policy" in problems
    assert "unscoped_permissive_policy" in problems


def test_a_permissive_policy_beside_the_tenant_policy_is_reported() -> None:
    """Permissive policies are OR-ed, so an open one nullifies the strict one."""
    problems = _audit(
        _table(), [_policy(), _policy(name="probe_readonly", command="r", using="true", check=None)]
    )

    assert "unscoped_permissive_policy" in problems


def test_a_read_only_tenant_policy_leaves_writes_uncovered() -> None:
    select_only = _policy(command="r", check=None)

    assert "commands_not_covered" in _audit(_table(), [select_only])


def test_per_command_policies_together_cover_everything() -> None:
    """Four narrow policies are as good as one FOR ALL, and must not be flagged."""
    policies = [
        _policy(name="probe_select", command="r", check=None),
        _policy(name="probe_insert", command="a", using=None),
        _policy(name="probe_update", command="w"),
        _policy(name="probe_delete", command="d", check=None),
    ]

    # The INSERT policy has no USING clause, which is how PostgreSQL stores it:
    # it is enforced entirely through WITH CHECK.
    assert _audit(_table(), policies) == set()


def test_for_all_without_with_check_is_not_a_finding() -> None:
    """PostgreSQL reuses USING as the write check when WITH CHECK is omitted.

    Pinned because the obvious-looking check — "a write policy needs a WITH
    CHECK" — is wrong, and would fire on all thirteen CRM tables at once.
    """
    assert _audit(_table(), [_policy(check=None)]) == set()


def test_a_write_policy_that_does_not_scope_new_rows_is_reported() -> None:
    """USING filters what you can see; the check is what stops you planting rows."""
    open_writes = _policy(check="true")

    problems = _audit(_table(), [open_writes])

    assert "unscoped_permissive_policy" in problems
    assert "no_tenant_policy" in problems


def test_a_nullable_tenant_column_is_reported() -> None:
    assert "tenant_column_nullable" in _audit(
        _table(tenant_column_not_null=False), [_policy()]
    )


# --- Tables not carrying organization_id ------------------------------------


def test_an_undocumented_table_without_the_tenant_column_is_reported() -> None:
    """A new CRM table is a finding until someone classifies it, either way."""
    problems = _audit(
        _table(has_tenant_column=False, tenant_column_not_null=False, rls_enabled=False,
               rls_forced=False)
    )

    assert "unclassified_table" in problems


def test_an_exemption_for_a_table_that_now_has_the_tenant_column_is_stale() -> None:
    problems = _audit(_table(), [_policy()], exemptions={"probe": "no longer true"})

    assert "stale_exemption" in problems


def test_an_exemption_naming_a_table_that_does_not_exist_is_stale() -> None:
    findings = audit_tenant_isolation((), exemptions={"ghost": "dropped three releases ago"})

    assert [finding.problem for finding in findings] == ["stale_exemption"]


# --- Assembly and reporting -------------------------------------------------


def test_policies_are_attached_to_the_table_they_belong_to() -> None:
    tables = build_table_security(
        "crm",
        [_table(name="accounts"), _table(name="contacts")],
        [{**_policy(), "table_name": "accounts"}],
    )
    by_name = {table.name: table for table in tables}

    assert len(by_name["accounts"].policies) == 1
    assert by_name["contacts"].policies == ()


def test_a_discovered_table_reports_its_qualified_name() -> None:
    (table,) = build_table_security("crm", [_table(name="accounts")], [])

    assert table.qualified_name == "crm.accounts"
    assert isinstance(table, TableSecurity)


def test_findings_render_with_the_table_and_the_reason() -> None:
    findings = audit_tenant_isolation(
        build_table_security("crm", [_table(rls_enabled=False)], []),
        exemptions=NO_EXEMPTIONS,
    )

    rendered = format_findings(findings)

    assert "crm.probe" in rendered
    assert TENANT_COLUMN in rendered


def test_a_clean_audit_renders_as_nothing() -> None:
    assert format_findings(()) == ""


# --- The CRM exemption registry ---------------------------------------------


def test_meetings_is_the_documented_crm_exemption() -> None:
    assert "meetings" in RLS_EXEMPT_TABLES


@pytest.mark.parametrize("table", sorted(RLS_EXEMPT_TABLES))
def test_every_exemption_carries_a_real_justification(table: str) -> None:
    """An exemption is a hole in tenant isolation; "n/a" is not a reason."""
    reason = RLS_EXEMPT_TABLES[table]

    assert len(reason.split()) >= 10, f"{table} is exempt without an explanation"
