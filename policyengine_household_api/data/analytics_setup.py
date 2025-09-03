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
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase
from flask_sqlalchemy import SQLAlchemy

logger = logging.getLogger(__name__)

# Global variable to store whether analytics is enabled
_analytics_enabled = None
_connector = None


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

    # Check if we're in debug mode
    if get_config_value("app.debug", False):
        from policyengine_household_api.constants import REPO

        db_url = (
            REPO / "policyengine_household_api" / "data" / "policyengine.db"
        )
        if Path(db_url).exists():
            Path(db_url).unlink()
        if not Path(db_url).exists():
            Path(db_url).touch()
        app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:////" + str(db_url)
    else:
        app.config["SQLALCHEMY_DATABASE_URI"] = "mysql+pymysql://"
        app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"creator": getconn}

    db.init_app(app)

    with app.app_context():
        db.create_all()


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


def get_analytics_connector():
    """
    Get the Google Cloud SQL connector for analytics.
    Returns None if analytics is disabled.

    Returns:
        Connector or None: The connector instance if analytics is enabled, None otherwise
    """
    global _connector

    if not is_analytics_enabled():
        return None

    if _connector is None:
        try:
            _connector = Connector()
        except Exception as e:
            logger.error(f"Failed to initialize analytics connector: {e}")
            return None

    return _connector


def getconn():
    """
    Get a connection to the analytics database.
    Returns None if analytics is disabled.

    Returns:
        Connection or None: Database connection if analytics is enabled, None otherwise
    """
    if not is_analytics_enabled():
        return None

    connector = get_analytics_connector()
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
            db="user_analytics",
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
