"""
Unit tests for the analytics setup module.
"""

import logging
from unittest.mock import patch, MagicMock, Mock
import pytest
from policyengine_household_api.data.analytics_setup import (
    is_analytics_enabled,
    get_analytics_connector,
    getconn,
    cleanup,
)


class TestIsAnalyticsEnabled:
    """Test the is_analytics_enabled function."""

    @patch("policyengine_household_api.data.analytics_setup.create_analytics_guard")
    def test__given_analytics_enabled__returns_true_and_logs(
        self, mock_create_guard, caplog
    ):
        """Test that analytics enabled returns True and logs appropriately."""
        # Set up mock guard
        mock_guard = MagicMock()
        mock_guard.check.return_value = (
            True,
            {
                "user_analytics_db_connection_name": "project:region:instance",
                "user_analytics_db_username": "user",
                "user_analytics_db_password": "pass",
            },
        )
        mock_create_guard.return_value = mock_guard

        # Reset module state
        import policyengine_household_api.data.analytics_setup as analytics_module

        analytics_module._analytics_enabled = None
        analytics_module._analytics_context = None

        with caplog.at_level(logging.INFO):
            result = is_analytics_enabled()

        assert result is True
        assert "User analytics is ENABLED" in caplog.text

    @patch("policyengine_household_api.data.analytics_setup.create_analytics_guard")
    def test__given_analytics_disabled__returns_false_and_logs(
        self, mock_create_guard, caplog
    ):
        """Test that analytics disabled returns False and logs appropriately."""
        # Set up mock guard
        mock_guard = MagicMock()
        mock_guard.check.return_value = (False, {"missing_vars": ["USER_ANALYTICS_DB_CONNECTION_NAME"]})
        mock_create_guard.return_value = mock_guard

        # Reset module state
        import policyengine_household_api.data.analytics_setup as analytics_module

        analytics_module._analytics_enabled = None
        analytics_module._analytics_context = None

        with caplog.at_level(logging.INFO):
            result = is_analytics_enabled()

        assert result is False
        assert "User analytics is DISABLED (opt-in required)" in caplog.text

    @patch("policyengine_household_api.data.analytics_setup.create_analytics_guard")
    def test__given_analytics_already_checked__returns_cached_value(
        self, mock_create_guard
    ):
        """Test that is_analytics_enabled caches its result."""
        # Set up mock guard
        mock_guard = MagicMock()
        mock_guard.check.return_value = (True, {})
        mock_create_guard.return_value = mock_guard

        # Reset module state
        import policyengine_household_api.data.analytics_setup as analytics_module

        analytics_module._analytics_enabled = None
        analytics_module._analytics_context = None

        # First call
        result1 = is_analytics_enabled()
        # Second call
        result2 = is_analytics_enabled()

        assert result1 is True
        assert result2 is True
        # Guard should only be created and checked once
        mock_create_guard.assert_called_once()
        mock_guard.check.assert_called_once()


class TestGetAnalyticsConnector:
    """Test the get_analytics_connector function."""

    @patch("policyengine_household_api.data.analytics_setup.create_analytics_guard")
    def test__given_analytics_disabled__returns_none(self, mock_create_guard):
        """Test that connector returns None when analytics is disabled."""
        # Set up mock guard
        mock_guard = MagicMock()
        mock_guard.check.return_value = (False, {})
        mock_create_guard.return_value = mock_guard

        # Reset module state
        import policyengine_household_api.data.analytics_setup as analytics_module

        analytics_module._analytics_enabled = None
        analytics_module._analytics_context = None
        analytics_module._connector = None

        result = get_analytics_connector()

        assert result is None

    @patch("policyengine_household_api.data.analytics_setup.Connector")
    @patch("policyengine_household_api.data.analytics_setup.create_analytics_guard")
    def test__given_analytics_enabled__creates_and_returns_connector(
        self, mock_create_guard, mock_connector_class
    ):
        """Test that connector is created when analytics is enabled."""
        # Set up mock guard
        mock_guard = MagicMock()
        mock_guard.check.return_value = (True, {})
        mock_create_guard.return_value = mock_guard

        # Set up mock connector
        mock_connector_instance = MagicMock()
        mock_connector_class.return_value = mock_connector_instance

        # Reset module state
        import policyengine_household_api.data.analytics_setup as analytics_module

        analytics_module._analytics_enabled = None
        analytics_module._analytics_context = None
        analytics_module._connector = None

        result = get_analytics_connector()

        assert result is mock_connector_instance
        mock_connector_class.assert_called_once()

    @patch("policyengine_household_api.data.analytics_setup.Connector")
    @patch("policyengine_household_api.data.analytics_setup.create_analytics_guard")
    def test__given_connector_already_exists__returns_cached_connector(
        self, mock_create_guard, mock_connector_class
    ):
        """Test that existing connector is reused."""
        # Set up mock guard
        mock_guard = MagicMock()
        mock_guard.check.return_value = (True, {})
        mock_create_guard.return_value = mock_guard

        # Set up mock connector
        mock_connector_instance = MagicMock()
        mock_connector_class.return_value = mock_connector_instance

        # Reset module state
        import policyengine_household_api.data.analytics_setup as analytics_module

        analytics_module._analytics_enabled = None
        analytics_module._analytics_context = None
        analytics_module._connector = None

        # First call creates connector
        result1 = get_analytics_connector()
        # Second call reuses connector
        result2 = get_analytics_connector()

        assert result1 is mock_connector_instance
        assert result2 is mock_connector_instance
        # Connector should only be created once
        mock_connector_class.assert_called_once()

    @patch("policyengine_household_api.data.analytics_setup.create_analytics_guard")
    def test__given_connector_import_fails__returns_none_and_logs_error(
        self, mock_create_guard, caplog
    ):
        """Test that import errors are handled gracefully."""
        # Set up mock guard
        mock_guard = MagicMock()
        mock_guard.check.return_value = (True, {})
        mock_create_guard.return_value = mock_guard

        # Reset module state
        import policyengine_household_api.data.analytics_setup as analytics_module

        analytics_module._analytics_enabled = None
        analytics_module._analytics_context = None
        analytics_module._connector = None

        with patch(
            "policyengine_household_api.data.analytics_setup.Connector",
            side_effect=ImportError("Module not found"),
        ):
            with caplog.at_level(logging.ERROR):
                result = get_analytics_connector()

        assert result is None
        assert "Failed to initialize analytics connector" in caplog.text


class TestGetConn:
    """Test the getconn function."""

    @patch("policyengine_household_api.data.analytics_setup.create_analytics_guard")
    def test__given_analytics_disabled__returns_none(self, mock_create_guard):
        """Test that getconn returns None when analytics is disabled."""
        # Set up mock guard
        mock_guard = MagicMock()
        mock_guard.check.return_value = (False, {})
        mock_create_guard.return_value = mock_guard

        # Reset module state
        import policyengine_household_api.data.analytics_setup as analytics_module

        analytics_module._analytics_enabled = None
        analytics_module._analytics_context = None

        result = getconn()

        assert result is None

    @patch("policyengine_household_api.data.analytics_setup.IPTypes")
    @patch("policyengine_household_api.data.analytics_setup.Connector")
    @patch("policyengine_household_api.data.analytics_setup.create_analytics_guard")
    def test__given_valid_configuration__creates_connection_successfully(
        self, mock_create_guard, mock_connector_class, mock_ip_types
    ):
        """Test successful connection creation with valid configuration."""
        # Set up mock guard with full context
        mock_guard = MagicMock()
        mock_guard.check.return_value = (
            True,
            {
                "user_analytics_db_connection_name": "project:region:instance",
                "user_analytics_db_username": "testuser",
                "user_analytics_db_password": "testpass",
            },
        )
        mock_create_guard.return_value = mock_guard

        # Set up mock connector
        mock_connector_instance = MagicMock()
        mock_connection = MagicMock()
        mock_connector_instance.connect.return_value = mock_connection
        mock_connector_class.return_value = mock_connector_instance

        # Set up IP types
        mock_ip_types.PUBLIC = "PUBLIC"

        # Reset module state
        import policyengine_household_api.data.analytics_setup as analytics_module

        analytics_module._analytics_enabled = None
        analytics_module._analytics_context = None
        analytics_module._connector = None

        result = getconn()

        assert result is mock_connection
        mock_connector_instance.connect.assert_called_once_with(
            "project:region:instance",
            "pymysql",
            user="testuser",
            password="testpass",
            db="user_analytics",
            ip_type="PUBLIC",
        )

    @patch("policyengine_household_api.data.analytics_setup.Connector")
    @patch("policyengine_household_api.data.analytics_setup.create_analytics_guard")
    def test__given_missing_connection_name__returns_none_and_logs_error(
        self, mock_create_guard, mock_connector_class, caplog
    ):
        """Test that missing connection_name is handled properly."""
        # Set up mock guard with missing connection_name
        mock_guard = MagicMock()
        mock_guard.check.return_value = (
            True,
            {
                "user_analytics_db_username": "testuser",
                "user_analytics_db_password": "testpass",
            },
        )
        mock_create_guard.return_value = mock_guard

        # Set up mock connector
        mock_connector_instance = MagicMock()
        mock_connector_class.return_value = mock_connector_instance

        # Reset module state
        import policyengine_household_api.data.analytics_setup as analytics_module

        analytics_module._analytics_enabled = None
        analytics_module._analytics_context = None
        analytics_module._connector = None

        with caplog.at_level(logging.ERROR):
            result = getconn()

        assert result is None
        assert "Analytics enabled but connection_name not configured" in caplog.text

    @patch("policyengine_household_api.data.analytics_setup.Connector")
    @patch("policyengine_household_api.data.analytics_setup.create_analytics_guard")
    def test__given_missing_username__returns_none_and_logs_error(
        self, mock_create_guard, mock_connector_class, caplog
    ):
        """Test that missing username is handled properly."""
        # Set up mock guard with missing username
        mock_guard = MagicMock()
        mock_guard.check.return_value = (
            True,
            {
                "user_analytics_db_connection_name": "project:region:instance",
                "user_analytics_db_password": "testpass",
            },
        )
        mock_create_guard.return_value = mock_guard

        # Set up mock connector
        mock_connector_instance = MagicMock()
        mock_connector_class.return_value = mock_connector_instance

        # Reset module state
        import policyengine_household_api.data.analytics_setup as analytics_module

        analytics_module._analytics_enabled = None
        analytics_module._analytics_context = None
        analytics_module._connector = None

        with caplog.at_level(logging.ERROR):
            result = getconn()

        assert result is None
        assert "Analytics enabled but username not configured" in caplog.text

    @patch("policyengine_household_api.data.analytics_setup.Connector")
    @patch("policyengine_household_api.data.analytics_setup.create_analytics_guard")
    def test__given_missing_password__returns_none_and_logs_error(
        self, mock_create_guard, mock_connector_class, caplog
    ):
        """Test that missing password is handled properly."""
        # Set up mock guard with missing password
        mock_guard = MagicMock()
        mock_guard.check.return_value = (
            True,
            {
                "user_analytics_db_connection_name": "project:region:instance",
                "user_analytics_db_username": "testuser",
            },
        )
        mock_create_guard.return_value = mock_guard

        # Set up mock connector
        mock_connector_instance = MagicMock()
        mock_connector_class.return_value = mock_connector_instance

        # Reset module state
        import policyengine_household_api.data.analytics_setup as analytics_module

        analytics_module._analytics_enabled = None
        analytics_module._analytics_context = None
        analytics_module._connector = None

        with caplog.at_level(logging.ERROR):
            result = getconn()

        assert result is None
        assert "Analytics enabled but password not configured" in caplog.text

    @patch("policyengine_household_api.data.analytics_setup.IPTypes")
    @patch("policyengine_household_api.data.analytics_setup.Connector")
    @patch("policyengine_household_api.data.analytics_setup.create_analytics_guard")
    def test__given_connection_error__returns_none_and_logs_error(
        self, mock_create_guard, mock_connector_class, mock_ip_types, caplog
    ):
        """Test that connection errors are handled gracefully."""
        # Set up mock guard with full context
        mock_guard = MagicMock()
        mock_guard.check.return_value = (
            True,
            {
                "user_analytics_db_connection_name": "project:region:instance",
                "user_analytics_db_username": "testuser",
                "user_analytics_db_password": "testpass",
            },
        )
        mock_create_guard.return_value = mock_guard

        # Set up mock connector to raise error
        mock_connector_instance = MagicMock()
        mock_connector_instance.connect.side_effect = Exception("Connection failed")
        mock_connector_class.return_value = mock_connector_instance

        # Set up IP types
        mock_ip_types.PUBLIC = "PUBLIC"

        # Reset module state
        import policyengine_household_api.data.analytics_setup as analytics_module

        analytics_module._analytics_enabled = None
        analytics_module._analytics_context = None
        analytics_module._connector = None

        with caplog.at_level(logging.ERROR):
            result = getconn()

        assert result is None
        assert "Failed to connect to analytics database" in caplog.text


class TestCleanup:
    """Test the cleanup function."""

    def test__given_no_connector__cleanup_does_nothing(self):
        """Test that cleanup works when no connector exists."""
        # Reset module state
        import policyengine_household_api.data.analytics_setup as analytics_module

        analytics_module._connector = None

        # Should not raise any errors
        cleanup()

        assert analytics_module._connector is None

    def test__given_existing_connector__cleanup_closes_and_clears_it(self):
        """Test that cleanup closes the connector properly."""
        # Set up mock connector
        mock_connector = MagicMock()

        # Reset module state
        import policyengine_household_api.data.analytics_setup as analytics_module

        analytics_module._connector = mock_connector

        cleanup()

        mock_connector.close.assert_called_once()
        assert analytics_module._connector is None

    def test__given_connector_close_fails__cleanup_still_clears_it(self):
        """Test that cleanup handles close errors gracefully."""
        # Set up mock connector that raises on close
        mock_connector = MagicMock()
        mock_connector.close.side_effect = Exception("Close failed")

        # Reset module state
        import policyengine_household_api.data.analytics_setup as analytics_module

        analytics_module._connector = mock_connector

        # Should not raise error
        cleanup()

        mock_connector.close.assert_called_once()
        assert analytics_module._connector is None


class TestModuleLevelState:
    """Test module-level state management."""

    @patch("policyengine_household_api.data.analytics_setup.create_analytics_guard")
    def test__given_multiple_function_calls__state_is_consistent(
        self, mock_create_guard
    ):
        """Test that module state remains consistent across function calls."""
        # Set up mock guard
        mock_guard = MagicMock()
        mock_guard.check.return_value = (
            True,
            {
                "user_analytics_db_connection_name": "project:region:instance",
                "user_analytics_db_username": "testuser",
                "user_analytics_db_password": "testpass",
            },
        )
        mock_create_guard.return_value = mock_guard

        # Reset module state
        import policyengine_household_api.data.analytics_setup as analytics_module

        analytics_module._analytics_enabled = None
        analytics_module._analytics_context = None
        analytics_module._connector = None

        # First check enables analytics
        is_enabled1 = is_analytics_enabled()
        assert is_enabled1 is True

        # Context should be available for other functions
        with patch(
            "policyengine_household_api.data.analytics_setup.Connector"
        ) as mock_connector_class:
            mock_connector = MagicMock()
            mock_connector_class.return_value = mock_connector

            connector = get_analytics_connector()
            assert connector is mock_connector

        # Second check should use cached value
        is_enabled2 = is_analytics_enabled()
        assert is_enabled2 is True

        # Guard should only be created once
        mock_create_guard.assert_called_once()


class TestAnalyticsExplicitlyDisabled:
    """Test analytics behavior when explicitly disabled via ANALYTICS_ENABLED=false."""

    @patch("policyengine_household_api.data.analytics_setup.create_analytics_guard")
    def test__given_explicitly_disabled__returns_false_even_with_credentials(
        self, mock_create_guard, caplog
    ):
        """Test that ANALYTICS_ENABLED=false overrides presence of credentials."""
        # Set up mock guard that returns disabled (explicitly disabled via env var)
        mock_guard = MagicMock()
        mock_guard.check.return_value = (False, {})
        mock_create_guard.return_value = mock_guard

        # Reset module state
        import policyengine_household_api.data.analytics_setup as analytics_module

        analytics_module._analytics_enabled = None
        analytics_module._analytics_context = None

        with caplog.at_level(logging.INFO):
            result = is_analytics_enabled()

        assert result is False
        assert "User analytics is DISABLED (opt-in required)" in caplog.text


class TestAnalyticsExplicitlyEnabled:
    """Test analytics behavior when explicitly enabled via ANALYTICS_ENABLED=true."""

    @patch("policyengine_household_api.data.analytics_setup.create_analytics_guard")
    def test__given_explicitly_enabled_with_creds__analytics_is_enabled(
        self, mock_create_guard, caplog
    ):
        """Test that ANALYTICS_ENABLED=true with credentials enables analytics."""
        # Set up mock guard
        mock_guard = MagicMock()
        mock_guard.check.return_value = (
            True,
            {
                "user_analytics_db_connection_name": "project:region:instance",
                "user_analytics_db_username": "user",
                "user_analytics_db_password": "pass",
                "explicitly_enabled": True,
            },
        )
        mock_create_guard.return_value = mock_guard

        # Reset module state
        import policyengine_household_api.data.analytics_setup as analytics_module

        analytics_module._analytics_enabled = None
        analytics_module._analytics_context = None

        with caplog.at_level(logging.INFO):
            result = is_analytics_enabled()

        assert result is True
        assert "User analytics is ENABLED" in caplog.text