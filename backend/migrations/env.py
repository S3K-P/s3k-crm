"""Alembic environment — async SQLAlchemy 2.0 (ADR-006).

The database URL comes from application settings, and the target metadata is
the same ``Base.metadata`` the runtime maps against (see ``app.core.metadata``
for the object and ``app.schema`` for the model registrations that populate
it). Nothing is duplicated between migrations and runtime.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig
from typing import Any

from alembic import context
from sqlalchemy import Connection, pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.core.config import get_settings

# Importing app.schema (rather than app.core.metadata directly) is what loads
# every models module and registers its tables on the shared metadata.
from app.schema import target_metadata

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Credentials are injected at runtime, never stored in alembic.ini.
config.set_main_option("sqlalchemy.url", get_settings().database_url)


def _configure_kwargs() -> dict[str, Any]:
    return {
        "target_metadata": target_metadata,
        "compare_type": True,
        "compare_server_default": True,
        # Required so future RLS-related and tenant tables migrate predictably.
        "include_schemas": True,
    }


def run_migrations_offline() -> None:
    """Emit SQL to stdout without connecting to a database."""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        **_configure_kwargs(),
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, **_configure_kwargs())
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations against a live async connection."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
