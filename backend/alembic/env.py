"""
Alembic environment (async / asyncpg).

This project is SQL-schema-first: the baseline schema lives in
`database/migrations/001_init.sql` (applied on DB init). Alembic adopts that baseline
via revision `0001_baseline` and manages *incremental* changes from there with
hand-written migrations (target_metadata is None — we don't autogenerate against the
partial per-service ORM models).
"""
import asyncio
import os
from logging.config import fileConfig

from sqlalchemy.ext.asyncio import async_engine_from_config
from sqlalchemy import pool
from alembic import context

config = context.config
config.set_main_option(
    "sqlalchemy.url",
    os.getenv("DATABASE_URL", "postgresql+asyncpg://pdfuser:pdfpass@localhost:5432/pdfeditor"),
)
if config.config_file_name:
    fileConfig(config.config_file_name)

target_metadata = None


def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations():
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.", poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    context.configure(url=config.get_main_option("sqlalchemy.url"), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    asyncio.run(run_async_migrations())
