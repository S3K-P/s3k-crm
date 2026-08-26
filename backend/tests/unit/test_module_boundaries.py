"""Executable enforcement of the module-boundary rules.

Ruff's banned-api check catches boundary violations at lint time; this suite
catches them at test time too, including in files a lint exemption might cover.
See ARCHITECTURE-BOUNDARIES.md.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

APP_ROOT = Path(__file__).resolve().parents[2] / "app"
PLATFORM_ROOT = APP_ROOT / "platform"
PRODUCTS_ROOT = APP_ROOT / "products"
CORE_ROOT = APP_ROOT / "core"

PLATFORM_MODULES = (
    "auth",
    "organizations",
    "authorization",
    "documents",
    "audit",
    "notifications",
    "teams",
)
CRM_MODULES = (
    "accounts",
    "contacts",
    "leads",
    "opportunities",
    "activities",
    "tasks",
    "notes",
    "dashboard",
    "search",
)
MODULE_FILES = (
    "router.py",
    "service.py",
    "repository.py",
    "schemas.py",
    "models.py",
    "policies.py",
    "events.py",
)


def _imported_modules(path: Path) -> set[str]:
    """Return every module path imported by a Python source file."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            imported.add(node.module)
    return imported


def _python_files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)


@pytest.mark.parametrize("source", _python_files(PLATFORM_ROOT), ids=str)
def test_platform_never_imports_a_product(source: Path) -> None:
    """ADR-003: the Shared Platform must not depend on any product module."""
    offending = {name for name in _imported_modules(source) if name.startswith("app.products")}

    assert not offending, (
        f"{source.relative_to(APP_ROOT)} imports {sorted(offending)}. "
        "Platform must never import a product — see ARCHITECTURE-BOUNDARIES.md."
    )


@pytest.mark.parametrize("source", _python_files(CORE_ROOT), ids=str)
def test_core_never_imports_platform_or_products(source: Path) -> None:
    """Infrastructure sits below both layers and must not depend on either."""
    offending = {
        name
        for name in _imported_modules(source)
        if name.startswith(("app.platform", "app.products"))
    }

    assert not offending, f"{source.relative_to(APP_ROOT)} imports {sorted(offending)}"


@pytest.mark.parametrize("source", _python_files(PRODUCTS_ROOT), ids=str)
def test_products_do_not_reach_into_platform_internals(source: Path) -> None:
    """ADR-003: products consume Platform through ``service`` interfaces only."""
    forbidden_suffixes = (".repository", ".models")
    offending = {
        name
        for name in _imported_modules(source)
        if name.startswith("app.platform") and name.endswith(forbidden_suffixes)
    }

    assert not offending, (
        f"{source.relative_to(APP_ROOT)} imports Platform internals {sorted(offending)}. "
        "Use the module's service interface instead."
    )


@pytest.mark.parametrize("module", PLATFORM_MODULES)
def test_platform_module_has_the_standard_shape(module: str) -> None:
    for filename in MODULE_FILES:
        assert (PLATFORM_ROOT / module / filename).is_file(), f"missing {module}/{filename}"


@pytest.mark.parametrize("module", CRM_MODULES)
def test_crm_module_has_the_standard_shape(module: str) -> None:
    for filename in MODULE_FILES:
        assert (PRODUCTS_ROOT / "crm" / module / filename).is_file(), f"missing {module}/{filename}"


def test_no_crm_entity_lives_in_the_platform_layer() -> None:
    """ADR-004/ADR-008: CRM entities belong to the product, not the Platform."""
    crm_entities = ("Account", "Contact", "Lead", "Opportunity", "Opportunity Stage")
    platform_module_names = {p.name for p in PLATFORM_ROOT.iterdir() if p.is_dir()}

    for entity in crm_entities:
        assert entity.lower().replace(" ", "_") not in platform_module_names


def test_platform_and_crm_share_one_metadata() -> None:
    """ADR-007: one database, one migration history — a single MetaData object."""
    from app.core.database import Base
    from app.core.metadata import target_metadata

    assert target_metadata is Base.metadata
