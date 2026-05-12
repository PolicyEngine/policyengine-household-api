"""
Analytics database setup with opt-in configuration support.
This module provides conditional analytics database connectivity based on configuration.
"""

import os
import logging
from policyengine_household_api.utils import get_config_value
from google.cloud.sql.connector import Connector
from google.cloud.sql.connector import IPTypes
from pathlib import Path
from sqlalchemy import inspect
from sqlalchemy.orm import DeclarativeBase
from flask_sqlalchemy import SQLAlchemy

logger = logging.getLogger(__name__)

# Global variable to store whether analytics is enabled
_analytics_enabled = None
_analytics_schema_ready = True
_connector = None

ANALYTICS_DATABASE_URL_ENV_VAR = "ANALYTICS_DATABASE_URL"
ANALYTICS_DATABASE_NAME = "user_analytics"
ANALYTICS_ALEMBIC_HEAD = "20260512_0003"
REQUIRED_ANALYTICS_COLUMNS = {
    "visits": {
        "id",
        "client_id",
        "datetime",
        "api_version",
        "endpoint",
        "method",
        "content_length_bytes",
    },
    "calculate_requests": {
        "id",
        "visit_id",
        "request_uuid",
        "client_id",
        "api_version",
        "country_id",
        "model_version",
        "endpoint",
        "method",
        "content_length_bytes",
        "response_status_code",
        "distinct_variable_count",
        "unsupported_variable_count",
        "deprecated_allowlisted_variable_count",
        "created_at",
    },
    "calculate_request_variables": {
        "id",
        "request_id",
        "client_id",
        "created_at",
        "country_id",
        "api_version",
        "model_version",
        "response_status_code",
        "variable_name",
        "variable_name_truncated",
        "entity_type",
        "source",
        "period_granularity",
        "entity_count",
        "period_count",
        "occurrence_count",
        "availability_status",
    },
}


# Configure db schema, but don't initialize db itself
class Base(DeclarativeBase):
    pass


db = SQLAlchemy(model_class=Base)


def initialize_analytics_db_if_enabled(app):
    """
    Initialize database configuration for the Flask app, if enabled.
    Return a bool corresponding with whether or not it's enabled,
    as well as the SQLAlchemy instance if it is enabled or None if not.

    Args:
        app: Flask application instance
    """
    if not is_analytics_enabled():
        return

    database_uri = get_analytics_database_uri()
    app.config["SQLALCHEMY_DATABASE_URI"] = database_uri
    if database_uri == "mysql+pymysql://":
        app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"creator": getconn}

    db.init_app(app)

    with app.app_context():
        schema_ready = check_analytics_schema_ready()
        set_analytics_schema_ready(schema_ready)
        if not schema_ready:
            raise RuntimeError(
                "Analytics is enabled but the analytics database schema is "
                "not ready. Run `uv run alembic upgrade head` and verify "
                "database connectivity before starting the API."
            )


def get_local_analytics_database_path() -> Path:
    from policyengine_household_api.constants import REPO

    return REPO / "policyengine_household_api" / "data" / "policyengine.db"


def get_analytics_database_uri() -> str:
    database_url = os.getenv(
        ANALYTICS_DATABASE_URL_ENV_VAR
    ) or get_config_value("analytics.database.url", "")
    if database_url:
        return str(database_url)

    if get_config_value("app.debug", False):
        db_path = get_local_analytics_database_path()
        should_reset = os.getenv("RESET_ANALYTICS", "").lower() in (
            "1",
            "true",
            "yes",
        ) or get_config_value("analytics.reset", False)
        if should_reset and db_path.exists():
            db_path.unlink()
        db_path.parent.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{db_path}"

    return "mysql+pymysql://"


def set_analytics_schema_ready(is_ready: bool) -> None:
    global _analytics_schema_ready
    _analytics_schema_ready = is_ready


def is_analytics_schema_ready() -> bool:
    return _analytics_schema_ready


def check_analytics_schema_ready() -> bool:
    try:
        inspector = inspect(db.engine)
        missing = list(_missing_required_schema(inspector))
    except Exception as e:
        logger.error(f"Could not inspect analytics database schema: {e}")
        return False

    if missing:
        logger.error(
            "Analytics database schema is not ready; run "
            "`uv run alembic upgrade head`. Missing: " + ", ".join(missing)
        )
        return False

    try:
        alembic_version = _alembic_version()
    except Exception as e:
        logger.error(f"Could not inspect analytics migration version: {e}")
        return False

    if alembic_version != ANALYTICS_ALEMBIC_HEAD:
        logger.error(
            "Analytics database schema is not at Alembic head "
            f"{ANALYTICS_ALEMBIC_HEAD}; current revision is "
            f"{alembic_version or 'missing'}. Run `uv run alembic upgrade head`."
        )
        return False

    return True


def _missing_required_schema(inspector):
    required_columns = {"visits": REQUIRED_ANALYTICS_COLUMNS["visits"]}
    if _collect_variable_usage_enabled():
        required_columns["calculate_requests"] = REQUIRED_ANALYTICS_COLUMNS[
            "calculate_requests"
        ]
        required_columns["calculate_request_variables"] = (
            REQUIRED_ANALYTICS_COLUMNS["calculate_request_variables"]
        )

    for table_name, column_names in required_columns.items():
        if not inspector.has_table(table_name):
            yield table_name
            continue

        existing_columns = {
            column["name"] for column in inspector.get_columns(table_name)
        }
        for missing_column in sorted(column_names - existing_columns):
            yield f"{table_name}.{missing_column}"


def _collect_variable_usage_enabled() -> bool:
    value = get_config_value("analytics.collect_variable_usage", True)
    if isinstance(value, str):
        return value.lower() not in {"0", "false", "no"}
    return bool(value)


def _alembic_version() -> str | None:
    inspector = inspect(db.engine)
    if not inspector.has_table("alembic_version"):
        return None

    with db.engine.connect() as connection:
        return connection.exec_driver_sql(
            "SELECT version_num FROM alembic_version"
        ).scalar()


def is_analytics_enabled() -> bool:
    """
    Check if analytics is enabled based on configuration.

    Returns:
        bool: True if analytics is enabled, False otherwise
    """
    global _analytics_enabled

    if _analytics_enabled is not None:
        return _analytics_enabled

    # Try to get from config first (future use when app migrates to ConfigLoader)
    _analytics_enabled = get_config_value("analytics.enabled", False)
    return _analytics_enabled


def get_analytics_connector(require_analytics_enabled: bool = True):
    """
    Get the Google Cloud SQL connector for analytics.
    Returns None if analytics is disabled.

    Returns:
        Connector or None: The connector instance if analytics is enabled, None otherwise
    """
    global _connector

    if require_analytics_enabled and not is_analytics_enabled():
        return None

    if _connector is None:
        try:
            _connector = Connector()
        except Exception as e:
            logger.error(f"Failed to initialize analytics connector: {e}")
            return None

    return _connector


def getconn(require_analytics_enabled: bool = True):
    """
    Get a connection to the analytics database.
    Returns None if analytics is disabled.

    Returns:
        Connection or None: Database connection if analytics is enabled, None otherwise
    """
    if require_analytics_enabled and not is_analytics_enabled():
        return None

    connector = get_analytics_connector(require_analytics_enabled)
    if not connector:
        return None

    try:
        connection_name = get_config_value(
            "analytics.database.connection_name",
        )
        username = get_config_value(
            "analytics.database.username",
        )
        password = get_config_value(
            "analytics.database.password",
        )

        if not connection_name or not username or not password:
            logger.error(
                "Analytics enabled but problem with one or more of the following configuration values: connection_name, username, password"
            )
            return None

        conn = connector.connect(
            connection_name,
            "pymysql",
            user=username,
            password=password,
            db=ANALYTICS_DATABASE_NAME,
            ip_type=IPTypes.PUBLIC,
        )

        return conn

    except Exception as e:
        logger.error(f"Failed to connect to analytics database: {e}")
        return None


def cleanup():
    """Clean up the analytics connector if it exists."""
    global _connector
    if _connector:
        try:
            _connector.close()
        except Exception:
            pass
        _connector = None
