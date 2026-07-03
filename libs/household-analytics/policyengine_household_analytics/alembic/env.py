"""Alembic environment for the household API analytics database."""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool, text

from policyengine_household_analytics.analytics_setup import (  # noqa: E402
    get_analytics_database_uri,
    getconn,
)
from policyengine_household_analytics.analytics_setup import db  # noqa: E402
import policyengine_household_analytics.orm  # noqa: F401,E402


config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = db.metadata


def _database_uri() -> str:
    x_args = context.get_x_argument(as_dictionary=True)
    return x_args.get("database_url") or get_analytics_database_uri()


def run_migrations_offline() -> None:
    context.configure(
        url=_database_uri(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def _run_migrations_with_lock(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=connection.dialect.name == "sqlite",
    )

    if connection.dialect.name != "mysql":
        with context.begin_transaction():
            context.run_migrations()
        return

    lock_name = "policyengine_household_api_alembic"
    lock_acquired = connection.execute(
        text("SELECT GET_LOCK(:lock_name, 30)"),
        {"lock_name": lock_name},
    ).scalar()
    if lock_acquired != 1:
        raise RuntimeError("Could not acquire analytics migration lock")

    try:
        with context.begin_transaction():
            context.run_migrations()
    finally:
        connection.execute(
            text("SELECT RELEASE_LOCK(:lock_name)"),
            {"lock_name": lock_name},
        )


def run_migrations_online() -> None:
    database_uri = _database_uri()
    engine_kwargs = {"poolclass": pool.NullPool}
    if database_uri == "mysql+pymysql://":
        engine_kwargs["creator"] = lambda: getconn(
            require_analytics_enabled=False
        )

    connectable = create_engine(database_uri, **engine_kwargs)

    with connectable.connect() as connection:
        _run_migrations_with_lock(connection)


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
