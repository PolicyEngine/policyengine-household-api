from __future__ import annotations

from sqlalchemy import create_engine, inspect
from sqlalchemy.pool import NullPool

from policyengine_household_api.data.analytics_setup import (
    get_analytics_database_uri,
    getconn,
)


def current_analytics_revision() -> str | None:
    database_uri = get_analytics_database_uri()
    engine_kwargs = {"poolclass": NullPool}
    if database_uri == "mysql+pymysql://":
        engine_kwargs["creator"] = lambda: getconn(
            require_analytics_enabled=False
        )

    engine = create_engine(database_uri, **engine_kwargs)
    try:
        inspector = inspect(engine)
        if not inspector.has_table("alembic_version"):
            return None

        with engine.connect() as connection:
            return connection.exec_driver_sql(
                "SELECT version_num FROM alembic_version"
            ).scalar()
    finally:
        engine.dispose()


def main() -> None:
    revision = current_analytics_revision()
    if revision:
        print(revision)


if __name__ == "__main__":
    main()
