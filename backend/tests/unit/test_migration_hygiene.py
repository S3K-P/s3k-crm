"""Migrations must be snapshots of history, not readers of living code.

This exists because the opposite cost us a working from-zero migration.

Revision ``8224845a67ac`` seeded the permission catalogue by importing
``PERMISSION_ACTIONS`` and friends from ``app.platform.authorization.catalog``,
so "the database can never disagree with the code". Adding ``VIEW_ALL`` to that
catalogue (revision ``20260819_0200``) then broke a **fresh** database: the old
revision tried to insert a value into an enum whose ``CREATE TYPE`` — a few
hundred lines below, correctly pinned — did not contain it.

    invalid input value for enum platform.permission_action: "VIEW_ALL"

Every existing database was fine, because the seed had already run there. Only
a run from zero could catch it, and nothing ran from zero.

The rule this pins: a migration may import stateless schema *helpers*, but
never a module whose contents are business vocabulary that later revisions are
expected to change.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

MIGRATIONS = Path(__file__).resolve().parents[2] / "migrations" / "versions"

#: Application modules a migration may import. These are DDL helpers whose
#: behaviour is fixed; they carry no vocabulary a later revision would extend.
ALLOWED_APP_IMPORTS = frozenset({"app.core.rls"})


def _app_imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            modules.add(node.module)
    return {name for name in modules if name.startswith("app.")}


def _revisions() -> list[Path]:
    return sorted(p for p in MIGRATIONS.glob("*.py") if p.name != "__init__.py")


def test_there_are_revisions_to_check() -> None:
    """Guards the guard: an empty glob would make every case below vacuous."""
    assert _revisions(), f"no migrations found under {MIGRATIONS}"


@pytest.mark.parametrize("revision", _revisions(), ids=lambda p: p.stem[:40])
def test_a_migration_does_not_import_living_application_code(revision: Path) -> None:
    offending = _app_imports(revision) - ALLOWED_APP_IMPORTS

    assert not offending, (
        f"{revision.name} imports {sorted(offending)}. A migration is a snapshot of "
        "history: pin the values it needs as literals in the file instead, or a "
        "later edit to that module silently rewrites what this revision does."
    )
