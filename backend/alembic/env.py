"""Alembic environment configuration."""

import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# Import your Base and models here
from app.db.base import Base
from app.core.config import settings

# Import all models to ensure they are registered with Base.metadata
from app.models import Brand, BrandRequest, Filament, Preset, Printer, User  # noqa: F401

# this is the Alembic Config object
config = context.config

# Override sqlalchemy.url with settings from .env
# Экранируем % для Alembic (он интерпретирует % как интерполяцию)
database_url_escaped = settings.DATABASE_URL.replace('%', '%%')
config.set_main_option("sqlalchemy.url", database_url_escaped)

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """
    Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Run migrations with the given connection."""
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations in 'online' mode with async engine."""
    import socket
    
    # Retry logic for Docker network DNS resolution
    max_retries = 30
    retry_delay = 1
    
    for attempt in range(max_retries):
        try:
            connectable = async_engine_from_config(
                config.get_section(config.config_ini_section, {}),
                prefix="sqlalchemy.",
                poolclass=pool.NullPool,
            )

            async with connectable.connect() as connection:
                await connection.run_sync(do_run_migrations)

            await connectable.dispose()
            return  # Success, exit retry loop
            
        except (socket.gaierror, OSError, Exception) as e:
            if attempt < max_retries - 1:
                print(f"⚠️  Database connection attempt {attempt + 1}/{max_retries} failed: {e}")
                print(f"   Retrying in {retry_delay} seconds...")
                await asyncio.sleep(retry_delay)
            else:
                # Last attempt failed, raise the error
                raise


def run_migrations_online() -> None:
    """
    Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.
    """
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

