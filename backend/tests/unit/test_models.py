"""Shared model mixins produce the expected physical columns."""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.models import (
    NAMING_CONVENTION,
    TENANT_SETTING,
    AuthorshipMixin,
    SoftDeleteMixin,
    TenantMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)
from app.core.rls import tenant_policy_predicate


class _SampleRow(
    Base,
    UUIDPrimaryKeyMixin,
    TimestampMixin,
    AuthorshipMixin,
    SoftDeleteMixin,
    TenantMixin,
):
    """A throwaway mapping used only to inspect the generated table."""

    __tablename__ = "_mixin_sample"
    __table_args__ = {"schema": "platform"}

    label: Mapped[str] = mapped_column(default="")


TABLE = _SampleRow.__table__


def test_all_mixin_columns_are_present() -> None:
    assert set(TABLE.columns.keys()) == {
        "id",
        "created_at",
        "updated_at",
        "created_by_id",
        "updated_by_id",
        "deleted_at",
        "organization_id",
        "label",
    }


def test_primary_key_is_uuid_with_server_side_uuidv7() -> None:
    column = TABLE.columns["id"]

    assert column.primary_key
    assert isinstance(column.type, Uuid)
    assert "uuidv7()" in str(column.server_default.arg)


def test_timestamps_are_timezone_aware_and_not_nullable() -> None:
    for name in ("created_at", "updated_at"):
        column = TABLE.columns[name]
        assert column.type.timezone is True, f"{name} must be timezone-aware"
        assert column.nullable is False


def test_authorship_columns_are_nullable_and_not_foreign_keys() -> None:
    """Audit history must survive deletion of the referenced user."""
    for name in ("created_by_id", "updated_by_id"):
        column = TABLE.columns[name]
        assert column.nullable is True
        assert not column.foreign_keys


def test_soft_delete_column_is_nullable_and_indexed() -> None:
    column = TABLE.columns["deleted_at"]

    assert column.nullable is True
    assert column.index is True


def test_tenant_column_is_required_and_indexed() -> None:
    """organization_id is what every RLS policy filters on — it cannot be null."""
    column = TABLE.columns["organization_id"]

    assert column.nullable is False
    assert column.index is True
    assert isinstance(column.type, Uuid)


def test_is_deleted_reflects_the_timestamp() -> None:
    row = _SampleRow()
    assert row.is_deleted is False

    row.deleted_at = dt.datetime.now(dt.UTC)
    assert row.is_deleted is True


def test_python_side_default_generates_uuid7() -> None:
    generated = TABLE.columns["id"].default.arg(None)

    assert isinstance(generated, uuid.UUID)
    assert generated.version == 7


def test_metadata_uses_the_deterministic_naming_convention() -> None:
    assert Base.metadata.naming_convention == NAMING_CONVENTION


def test_rls_predicate_targets_the_tenant_setting_and_fails_closed() -> None:
    predicate = tenant_policy_predicate()

    assert TENANT_SETTING in predicate
    # The two-argument current_setting plus NULLIF is what makes an unset
    # context match zero rows instead of raising or matching everything.
    assert "true" in predicate
    assert "NULLIF" in predicate
