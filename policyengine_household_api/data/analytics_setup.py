"""
Analytics database setup with opt-in configuration support.
This module provides conditional analytics database connectivity based on configuration.
"""

import os
import logging
from policyengine_household_api.utils import get_config_value
from google.cloud.sql.connector import Connector, IPTypes

logger = logging.getLogger(__name__)

# Global variable to store whether analytics is enabled
_analytics_enabled = None
_connector = None


def is_analytics_enabled() -> bool:
    """
    Check if analytics is enabled based on configuration.

    Returns:
        bool: True if analytics is enabled, False otherwise
    """
    global _analytics_enabled

    if _analytics_enabled is not None:
        return _analytics_enabled

    _analytics_enabled = get_config_value("analytics.enabled", False)

    if _analytics_enabled:
        logger.info("User analytics is ENABLED")
    else:
        logger.info("User analytics is DISABLED (opt-in required)")

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
        # Get connection parameters from config or environment
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
                "Missing analytics database configuration value"
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
