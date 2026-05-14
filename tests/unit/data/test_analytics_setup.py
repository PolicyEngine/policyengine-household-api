"""
Unit tests for analytics_setup module.
Tests opt-in/opt-out scenarios and various configuration states.
"""

import pytest
import os


class TestAnalyticsEnabled:
    """Test the is_analytics_enabled function."""

    def test__given_no_config_set__analytics_disabled_by_default(
        self,
        reset_analytics_state,
        analytics_disabled_env,
        patch_get_config_value_returns_false,
    ):
        """Analytics should be disabled by default when no config is set."""
        from policyengine_household_api.data.analytics_setup import (
            is_analytics_enabled,
        )

        assert is_analytics_enabled() is False

    def test__given_config_explicitly_enables_analytics__analytics_is_enabled(
        self,
        reset_analytics_state,
        analytics_enabled_env,
        patch_get_config_value_returns_true,
    ):
        """Analytics should be enabled when config explicitly enables it."""
        from policyengine_household_api.data.analytics_setup import (
            is_analytics_enabled,
        )

        assert is_analytics_enabled() is True

    def test__given_analytics_enabled_env_var__analytics_is_enabled(
        self,
        reset_analytics_state,
        analytics_enabled_env,
        patch_get_config_value_returns_true,
    ):
        """Analytics should be enabled when ANALYTICS__ENABLED env var is set."""
        from policyengine_household_api.data.analytics_setup import (
            is_analytics_enabled,
        )

        assert is_analytics_enabled() is True

    def test__given_partial_credentials__analytics_remains_disabled(
        self,
        reset_analytics_state,
        analytics_partial_env,
        patch_get_config_value_raises_exception,
    ):
        """Analytics should remain disabled with only partial credentials."""
        from policyengine_household_api.data.analytics_setup import (
            is_analytics_enabled,
        )

        with pytest.raises(Exception, match="No config"):
            is_analytics_enabled()

    def test__given_analytics_state_checked_once__subsequent_checks_use_cached_value(
        self,
        reset_analytics_state,
        analytics_enabled_env,
        patch_get_config_value_returns_true,
    ):
        """Analytics state should be cached after first check."""
        from policyengine_household_api.data.analytics_setup import (
            is_analytics_enabled,
        )

        # First call
        result1 = is_analytics_enabled()
        assert result1 is True
        assert patch_get_config_value_returns_true.call_count == 1

        # Second call should use cached value
        result2 = is_analytics_enabled()
        assert result2 is True
        assert (
            patch_get_config_value_returns_true.call_count == 1
        )  # Not called again


class TestAnalyticsConnector:
    """Test the get_analytics_connector function."""

    def test__given_analytics_disabled__connector_returns_none(
        self,
        reset_analytics_state,
        analytics_disabled_env,
        patch_get_config_value_returns_false,
    ):
        """Connector should return None when analytics is disabled."""
        from policyengine_household_api.data.analytics_setup import (
            get_analytics_connector,
        )

        assert get_analytics_connector() is None

    def test__given_analytics_enabled__connector_is_initialized(
        self,
        reset_analytics_state,
        analytics_enabled_env,
        mock_google_connector,
        patch_get_config_value_returns_true,
    ):
        """Connector should be initialized when analytics is enabled."""
        from policyengine_household_api.data.analytics_setup import (
            get_analytics_connector,
        )

        connector = get_analytics_connector()
        assert connector is not None
        assert connector == mock_google_connector

    def test__given_connector_initialized__subsequent_calls_return_cached_instance(
        self,
        reset_analytics_state,
        analytics_enabled_env,
        patch_get_config_value_returns_true,
        patch_analytics_connector_class,
    ):
        """Connector should be cached after first initialization."""
        from policyengine_household_api.data.analytics_setup import (
            get_analytics_connector,
        )

        connector_class, _ = patch_analytics_connector_class

        connector1 = get_analytics_connector()
        assert connector_class.call_count == 1

        connector2 = get_analytics_connector()
        assert connector1 is connector2
        assert connector_class.call_count == 1

    def test__given_google_cloud_sql_library_not_available__connector_returns_none(
        self,
        reset_analytics_state,
        analytics_enabled_env,
        patch_get_config_value_returns_true,
        patch_google_connector_raises_import_error,
    ):
        """Connector should return None if Google Cloud SQL library not available."""
        from policyengine_household_api.data.analytics_setup import (
            get_analytics_connector,
        )

        connector = get_analytics_connector()
        assert connector is None


class TestGetConnection:
    """Test the getconn function."""

    def test__given_analytics_disabled__connection_returns_none(
        self,
        reset_analytics_state,
        analytics_disabled_env,
        patch_get_config_value_returns_false,
    ):
        """Connection should return None when analytics is disabled."""
        from policyengine_household_api.data.analytics_setup import getconn

        assert getconn() is None

    def test__given_valid_config__connection_succeeds(
        self,
        reset_analytics_state,
        analytics_enabled_env,
        mock_google_connector,
        patch_get_config_value_with_full_config,
        mock_pymysql_connection,
    ):
        """Connection should succeed with valid configuration."""
        from policyengine_household_api.data.analytics_setup import getconn

        mock_google_connector.connect.return_value = mock_pymysql_connection

        conn = getconn()
        assert conn == mock_pymysql_connection
        mock_google_connector.connect.assert_called_once()

    def test__given_missing_connection_name__connection_returns_none(
        self,
        reset_analytics_state,
        analytics_disabled_env,
        mock_google_connector,
        patch_get_config_value_missing_connection_name,
    ):
        """Connection should return None if connection_name is missing."""
        from policyengine_household_api.data.analytics_setup import getconn

        # Set up env with missing connection name
        os.environ["ANALYTICS__ENABLED"] = "true"
        os.environ["USER_ANALYTICS_DB_USERNAME"] = "test_user"
        os.environ["USER_ANALYTICS_DB_PASSWORD"] = "test_password"

        conn = getconn()
        assert conn is None

    def test__given_missing_username__connection_returns_none(
        self,
        reset_analytics_state,
        analytics_disabled_env,
        mock_google_connector,
        patch_get_config_value_missing_username,
    ):
        """Connection should return None if username is missing."""
        from policyengine_household_api.data.analytics_setup import getconn

        os.environ["ANALYTICS__ENABLED"] = "true"
        os.environ["USER_ANALYTICS_DB_CONNECTION_NAME"] = (
            "test-project:us-central1:test-instance"
        )
        os.environ["USER_ANALYTICS_DB_PASSWORD"] = "test_password"

        conn = getconn()
        assert conn is None

    def test__given_missing_password__connection_returns_none(
        self,
        reset_analytics_state,
        analytics_disabled_env,
        mock_google_connector,
        patch_get_config_value_missing_password,
    ):
        """Connection should return None if password is missing."""
        from policyengine_household_api.data.analytics_setup import getconn

        os.environ["ANALYTICS__ENABLED"] = "true"
        os.environ["USER_ANALYTICS_DB_CONNECTION_NAME"] = (
            "test-project:us-central1:test-instance"
        )
        os.environ["USER_ANALYTICS_DB_USERNAME"] = "test_user"

        conn = getconn()
        assert conn is None

    def test__given_connection_fails__connection_returns_none(
        self,
        reset_analytics_state,
        analytics_enabled_env,
        patch_get_config_value_with_full_config,
        patch_google_connector_with_connection_error,
    ):
        """Connection should return None if connection fails."""
        from policyengine_household_api.data.analytics_setup import getconn

        conn = getconn()
        assert conn is None


class TestAnalyticsDatabaseInitialization:
    def test__given_analytics_enabled__initialization_does_not_create_tables(
        self,
        reset_analytics_state,
        analytics_flask_app,
        patch_analytics_initialization_ready,
    ):
        from policyengine_household_api.data.analytics_setup import (
            initialize_analytics_db_if_enabled,
        )

        initialize_analytics_db_if_enabled(analytics_flask_app)

        assert (
            analytics_flask_app.config["SQLALCHEMY_DATABASE_URI"]
            == "sqlite:///:memory:"
        )
        patch_analytics_initialization_ready.assert_not_called()

    def test__given_schema_check_fails__initialization_raises(
        self,
        reset_analytics_state,
        analytics_flask_app,
        patch_analytics_initialization_schema_not_ready,
    ):
        from policyengine_household_api.data.analytics_setup import (
            initialize_analytics_db_if_enabled,
            is_analytics_schema_ready,
        )

        with pytest.raises(RuntimeError, match="Analytics is enabled"):
            initialize_analytics_db_if_enabled(analytics_flask_app)

        assert is_analytics_schema_ready() is False

    def test__missing_calculate_tables__schema_check_reports_missing_tables(
        self,
        reset_analytics_state,
    ):
        from policyengine_household_api.data.analytics_setup import (
            _missing_required_schema,
        )

        class FakeInspector:
            def has_table(self, table_name):
                return table_name == "visits"

            def get_columns(self, table_name):
                return [
                    {"name": "id"},
                    {"name": "client_id"},
                    {"name": "datetime"},
                    {"name": "api_version"},
                    {"name": "endpoint"},
                    {"name": "method"},
                    {"name": "content_length_bytes"},
                ]

        assert list(_missing_required_schema(FakeInspector())) == [
            "calculate_requests",
            "calculate_request_variables",
        ]

    def test__missing_alembic_version__schema_check_fails(
        self,
        reset_analytics_state,
        initialized_analytics_flask_app,
        patch_schema_check_missing_alembic_version,
    ):
        from policyengine_household_api.data.analytics_setup import (
            check_analytics_schema_ready,
        )

        with initialized_analytics_flask_app.app_context():
            assert check_analytics_schema_ready() is False

    def test__wrong_alembic_version__schema_check_fails(
        self,
        reset_analytics_state,
        initialized_analytics_flask_app,
        patch_schema_check_wrong_alembic_version,
    ):
        from policyengine_household_api.data.analytics_setup import (
            check_analytics_schema_ready,
        )

        with initialized_analytics_flask_app.app_context():
            assert check_analytics_schema_ready() is False

    def test__head_alembic_version__schema_check_passes(
        self,
        reset_analytics_state,
        initialized_analytics_flask_app,
        patch_schema_check_head_alembic_version,
    ):
        from policyengine_household_api.data.analytics_setup import (
            check_analytics_schema_ready,
        )

        with initialized_analytics_flask_app.app_context():
            assert check_analytics_schema_ready() is True


class TestAlembicRevisionCompatibility:
    def test__exact_minimum_revision__is_compatible(self):
        from policyengine_household_api.data.analytics_setup import (
            ANALYTICS_ALEMBIC_MINIMUM_REVISION,
            _alembic_revision_is_compatible,
        )

        assert _alembic_revision_is_compatible(
            ANALYTICS_ALEMBIC_MINIMUM_REVISION
        )

    def test__known_descendant_revision__is_compatible(self):
        from policyengine_household_api.data.analytics_setup import (
            _alembic_revision_is_compatible,
        )

        assert _alembic_revision_is_compatible(
            "20260512_0003",
            minimum_revision="20260508_0001",
        )

    def test__older_known_revision__is_not_compatible(self):
        from policyengine_household_api.data.analytics_setup import (
            _alembic_revision_is_compatible,
        )

        assert not _alembic_revision_is_compatible("20260508_0001")

    def test__future_timestamp_revision__is_compatible(self):
        from policyengine_household_api.data.analytics_setup import (
            _alembic_revision_is_compatible,
        )

        assert _alembic_revision_is_compatible("20990101_0001")

    def test__unknown_unordered_revision__is_not_compatible(self):
        from policyengine_household_api.data.analytics_setup import (
            _alembic_revision_is_compatible,
        )

        assert not _alembic_revision_is_compatible("not_a_real_revision")


class TestCleanup:
    """Test the cleanup function."""

    def test__given_connector_exists__cleanup_closes_connector(
        self, reset_analytics_state, mock_closeable_connector
    ):
        """Cleanup should close the connector if it exists."""
        from policyengine_household_api.data.analytics_setup import cleanup
        import policyengine_household_api.data.analytics_setup as analytics

        analytics._connector = mock_closeable_connector

        cleanup()

        mock_closeable_connector.close.assert_called_once()
        assert analytics._connector is None

    def test__given_no_connector__cleanup_handles_gracefully(
        self, reset_analytics_state
    ):
        """Cleanup should handle case where no connector exists."""
        from policyengine_household_api.data.analytics_setup import cleanup

        # Should not raise error
        cleanup()

    def test__given_close_raises_error__cleanup_still_clears_connector(
        self, reset_analytics_state, mock_closeable_connector
    ):
        """Cleanup should handle errors when closing connector."""
        from policyengine_household_api.data.analytics_setup import cleanup
        import policyengine_household_api.data.analytics_setup as analytics

        mock_closeable_connector.close.side_effect = Exception("Close failed")
        analytics._connector = mock_closeable_connector

        # Should not raise error
        cleanup()
        assert analytics._connector is None
