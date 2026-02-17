"""
PURPOSE: Alembic migration environment configuration.

Configures Alembic to work with async SQLAlchemy and PostgreSQL.
Automatically detects all models from app.models for migration generation.
"""

import asyncio
from logging.config import fileConfig
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine, AsyncEngine

from alembic import context

# Import Base and all models so Alembic detects them
from app.db.base import Base
from app.models import (
    MasterAccount,
    FollowerAccount,
    Trade,
    Strategy,
    RegimeState,
    CapitalAllocation,
    MLModel,
    ModelVersion,
    EventLog,
    SystemHealth,
)
from app.config.settings import settings

# Alembic config object for logging
config = context.config

# Interpret the config file for logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Target metadata for auto-generate support
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """
    PURPOSE: Run migrations in 'offline' mode.

    This configures the context with just a URL and not an Engine,
    though an Engine is acceptable here as well. By skipping the Engine
    creation we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.
    """
    url = settings.DATABASE_URL
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """
    PURPOSE: Execute migrations using async connection.

    Args:
        connection: SQLAlchemy async connection object
    """
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """
    PURPOSE: Create an async engine and run migrations.

    Creates an async engine configured for the current environment
    and executes all pending migrations.
    """
    engine: AsyncEngine = create_async_engine(
        settings.DATABASE_URL,
        echo=settings.DEBUG,
        poolclass=pool.NullPool,
    )

    async with engine.begin() as connection:
        await connection.run_sync(do_run_migrations)

    await engine.dispose()


def run_migrations_online() -> None:
    """
    PURPOSE: Run migrations in 'online' mode.

    In this scenario we need to create an Engine and associate
    a connection with the context.
    """
    if context.is_offline_mode():
        run_migrations_offline()
    else:
        asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
