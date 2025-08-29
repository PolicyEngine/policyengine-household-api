"""
Analytics database setup with opt-in configuration support.
This module provides conditional analytics database connectivity based on configuration.
"""

import logging
from policyengine_household_api.utils.env_var_guard import create_analytics_guard

logger = logging.getLogger(__name__)

# Global variable to store whether analytics is enabled and context
_analytics_enabled = None
_analytics_context = None
_connector = None


def is_analytics_enabled() -> bool:
    """
    Check if analytics is enabled based on configuration.

    Returns:
        bool: True if analytics is enabled, False otherwise
    """
    global _analytics_enabled, _analytics_context

    if _analytics_enabled is not None:
        return _analytics_enabled

    # Use analytics guard to check if analytics is enabled
    guard = create_analytics_guard()
    _analytics_enabled, _analytics_context = guard.check()

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
            from google.cloud.sql.connector import Connector

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
        # Get connection parameters from the context set by analytics guard
        global _analytics_context
        
        connection_name = _analytics_context.get('user_analytics_db_connection_name')
        username = _analytics_context.get('user_analytics_db_username')
        password = _analytics_context.get('user_analytics_db_password')

        if not connection_name:
            logger.error(
                "Analytics enabled but connection_name not configured"
            )
            return None
        if not username:
            logger.error("Analytics enabled but username not configured")
            return None
        if not password:
            logger.error("Analytics enabled but password not configured")
            return None

        from google.cloud.sql.connector import IPTypes

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
