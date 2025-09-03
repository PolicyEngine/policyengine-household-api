"""
Unit tests for the ConfigLoader class.
"""

import os
import pytest
import yaml
from pathlib import Path
from unittest.mock import patch
import logging

from policyengine_household_api.utils.config_loader import (
    ConfigLoader,
    get_config,
    get_config_value,
)
from tests.fixtures.utils.config_loader import (
    DEFAULT_CONFIG_DATA,
    EXTERNAL_CONFIG_DATA,
    CUSTOM_CONFIG_DATA,
    ENV_VAR_TEST_DATA,
    DOUBLE_UNDERSCORE_ENV_VARS,
    TYPE_CONVERSION_TEST_CASES,
    temp_custom_config,
    temp_default_config,
    temp_external_config,
    temp_empty_config,
    temp_invalid_yaml_config,
    clean_env,
    config_with_env_vars,
    config_with_double_underscore,
    config_with_mixed_env_vars,
    # CONFIG_VALUE_SETTINGS fixtures
    temp_valid_config_values_file,
    temp_config_with_variables,
    temp_missing_vars_config_values,
    temp_config_with_missing_var,
    temp_invalid_format_values_file,
    temp_invalid_key_number_values_file,
    temp_duplicate_keys_values_file,
    temp_config_with_duplicate_key,
    temp_empty_values_file,
    temp_complex_values_file,
    temp_config_with_complex_values,
    temp_realistic_values_file,
    temp_realistic_config_with_vars,
    temp_no_read_permission_values_file,
)


class TestConfigLoaderInitialization:
    """Test ConfigLoader initialization and basic setup."""

    def test__given_no_arguments__loader_initializes_with_defaults(self):
        """Test that ConfigLoader initializes with default values."""
        loader = ConfigLoader()

        assert loader.default_config_path == ConfigLoader.DEFAULT_CONFIG_PATH
        assert loader._config is None

    def test__given_custom_default_path__loader_uses_custom_path(self):
        """Test initialization with custom default config path."""
        CUSTOM_PATH = "/custom/path/config.yaml"
        loader = ConfigLoader(default_config_path=CUSTOM_PATH)

        assert loader.default_config_path == CUSTOM_PATH
        assert loader._config is None


class TestDefaultConfigLoading:
    """Test loading of default configuration files."""

    def test__given_valid_default_config__loader_loads_config_correctly(
        self, temp_default_config
    ):
        """Test loading a valid default configuration file."""
        loader = ConfigLoader(default_config_path=temp_default_config)
        config = loader.load()

        assert config["app"]["name"] == DEFAULT_CONFIG_DATA["app"]["name"]
        assert (
            config["app"]["environment"]
            == DEFAULT_CONFIG_DATA["app"]["environment"]
        )
        assert (
            config["database"]["provider"]
            == DEFAULT_CONFIG_DATA["database"]["provider"]
        )

    def test__given_missing_default_config__loader_returns_empty_dict(
        self, clean_env
    ):
        """Test behavior when default config file doesn't exist."""
        NON_EXISTENT_PATH = "/non/existent/config.yaml"
        loader = ConfigLoader(default_config_path=NON_EXISTENT_PATH)

        config = loader.load()
        assert config == {}

    def test__given_empty_default_config__loader_returns_empty_dict(
        self, temp_empty_config, clean_env
    ):
        """Test loading an empty default configuration file."""
        loader = ConfigLoader(default_config_path=temp_empty_config)
        config = loader.load()

        assert config == {}

    def test__given_config_already_loaded__subsequent_loads_return_cached_value(
        self, temp_default_config
    ):
        """Test that config is cached after first load."""
        loader = ConfigLoader(default_config_path=temp_default_config)

        # First load
        config1 = loader.load()
        # Second load should return cached value
        config2 = loader.load()

        assert config1 is config2  # Same object reference


class TestExternalConfigLoading:
    """Test loading of external configuration files."""

    def test__given_external_config_via_env_var__loader_loads_external_config(
        self, temp_external_config, clean_env
    ):
        """Test loading an external config file via CONFIG_FILE env var."""
        clean_env.setenv("CONFIG_FILE", temp_external_config)

        loader = ConfigLoader(default_config_path="/non/existent/path")
        config = loader.load()

        assert (
            config["app"]["environment"]
            == EXTERNAL_CONFIG_DATA["app"]["environment"]
        )
        assert (
            config["database"]["provider"]
            == EXTERNAL_CONFIG_DATA["database"]["provider"]
        )

    def test__given_no_config_file_env_var__loader_skips_external_config(
        self, temp_default_config, clean_env
    ):
        """Test that external config is not loaded when CONFIG_FILE is not set."""
        loader = ConfigLoader(default_config_path=temp_default_config)
        config = loader.load()

        # Should only have default config
        assert (
            config["app"]["environment"]
            == DEFAULT_CONFIG_DATA["app"]["environment"]
        )

    def test__given_nonexistent_external_config__loader_falls_back_to_default(
        self, temp_default_config, clean_env
    ):
        """Test behavior when external config file doesn't exist."""
        clean_env.setenv("CONFIG_FILE", "/non/existent/external.yaml")

        loader = ConfigLoader(default_config_path=temp_default_config)
        config = loader.load()

        # Should fall back to default config
        assert (
            config["app"]["environment"]
            == DEFAULT_CONFIG_DATA["app"]["environment"]
        )


class TestEnvironmentVariableOverrides:
    """Test environment variable override functionality."""

    def test__given_traditional_env_vars__config_maps_them_correctly(
        self, config_with_env_vars
    ):
        """Test that traditional PolicyEngine env vars are mapped correctly."""
        loader = ConfigLoader(default_config_path="/non/existent/path")
        config = loader.load()

        assert config["app"]["debug"] is True  # FLASK_DEBUG=1
        assert (
            config["analytics"]["database"]["connection_name"]
            == ENV_VAR_TEST_DATA["USER_ANALYTICS_DB_CONNECTION_NAME"]
        )
        assert (
            config["analytics"]["database"]["username"]
            == ENV_VAR_TEST_DATA["USER_ANALYTICS_DB_USERNAME"]
        )
        assert (
            config["analytics"]["database"]["password"]
            == ENV_VAR_TEST_DATA["USER_ANALYTICS_DB_PASSWORD"]
        )
        assert (
            config["auth"]["auth0"]["address"]
            == ENV_VAR_TEST_DATA["AUTH0_ADDRESS_NO_DOMAIN"]
        )
        assert (
            config["auth"]["auth0"]["audience"]
            == ENV_VAR_TEST_DATA["AUTH0_AUDIENCE_NO_DOMAIN"]
        )
        assert (
            config["ai"]["anthropic"]["api_key"]
            == ENV_VAR_TEST_DATA["ANTHROPIC_API_KEY"]
        )
        assert config["server"]["port"] == int(ENV_VAR_TEST_DATA["PORT"])

    def test__given_double_underscore_env_vars__config_parses_them_correctly(
        self, config_with_double_underscore
    ):
        """Test that double underscore notation works correctly."""
        loader = ConfigLoader(default_config_path="/non/existent/path")
        config = loader.load()

        assert (
            config["database"]["host"]
            == DOUBLE_UNDERSCORE_ENV_VARS["DATABASE__HOST"]
        )
        assert config["database"]["port"] == int(
            DOUBLE_UNDERSCORE_ENV_VARS["DATABASE__PORT"]
        )
        assert config["database"]["pool_size"] == int(
            DOUBLE_UNDERSCORE_ENV_VARS["DATABASE__POOL_SIZE"]
        )
        assert config["server"]["workers"] == int(
            DOUBLE_UNDERSCORE_ENV_VARS["SERVER__WORKERS"]
        )
        assert config["auth"]["enabled"] is True
        assert (
            config["auth"]["provider"]
            == DOUBLE_UNDERSCORE_ENV_VARS["AUTH__PROVIDER"]
        )
        assert (
            config["logging"]["level"]
            == DOUBLE_UNDERSCORE_ENV_VARS["LOGGING__LEVEL"]
        )

    def test__given_mixed_env_var_types__both_work_together(
        self, config_with_mixed_env_vars
    ):
        """Test that both traditional and double underscore env vars work together."""
        loader = ConfigLoader(default_config_path="/non/existent/path")
        config = loader.load()

        # Traditional mappings
        assert config["app"]["debug"] is True
        assert (
            config["analytics"]["database"]["username"]
            == ENV_VAR_TEST_DATA["USER_ANALYTICS_DB_USERNAME"]
        )

        # Double underscore mappings
        assert (
            config["database"]["host"]
            == DOUBLE_UNDERSCORE_ENV_VARS["DATABASE__HOST"]
        )
        assert config["server"]["workers"] == int(
            DOUBLE_UNDERSCORE_ENV_VARS["SERVER__WORKERS"]
        )


class TestConfigPriority:
    """Test configuration priority and merging."""

    def test__given_all_config_source_types__priority_order_is_correct(
        self, temp_default_config, temp_external_config, clean_env
    ):
        """Test that priority order is: env vars > external config > default config."""
        # Set up all three config sources
        clean_env.setenv("CONFIG_FILE", temp_external_config)
        clean_env.setenv("APP__ENVIRONMENT", "env-override")
        clean_env.setenv("DATABASE__HOST", "env-db-host")

        loader = ConfigLoader(default_config_path=temp_default_config)
        config = loader.load()

        # From default config (lowest priority)
        assert config["app"]["name"] == DEFAULT_CONFIG_DATA["app"]["name"]

        # From external config (overrides default)
        assert (
            config["app"]["debug"] is True
        )  # External overrides default's False

        # From env vars (highest priority)
        assert config["app"]["environment"] == "env-override"  # Env var wins
        assert config["database"]["host"] == "env-db-host"  # Env var wins

    def test__given_two_config_source_types__deep_merge_behavior_is_correct(
        self, temp_default_config, temp_external_config, clean_env
    ):
        """Test that configs are deep merged, not replaced entirely."""
        clean_env.setenv("CONFIG_FILE", temp_external_config)

        loader = ConfigLoader(default_config_path=temp_default_config)
        config = loader.load()

        # app.name from default should still exist even though external has app section
        assert config["app"]["name"] == DEFAULT_CONFIG_DATA["app"]["name"]
        # app.environment from external should override default
        assert (
            config["app"]["environment"]
            == EXTERNAL_CONFIG_DATA["app"]["environment"]
        )
        # server from default should still exist (not in external)
        assert (
            config["server"]["workers"]
            == DEFAULT_CONFIG_DATA["server"]["workers"]
        )


class TestValueConversion:
    """Test type conversion for string values."""

    @pytest.mark.parametrize(
        "input_value,expected_output", TYPE_CONVERSION_TEST_CASES
    )
    def test__given_string_values__appropriate_type_conversion_occurs(
        self, input_value, expected_output
    ):
        """Test that string values are converted to appropriate types."""
        loader = ConfigLoader()
        converted = loader._convert_value(input_value)
        assert converted == expected_output

    def test__given_nested_dict_values__values_are_set_properly(self):
        """Test setting nested values in dictionaries."""
        loader = ConfigLoader()
        config = {}

        TEST_PATH = "database.connection.pool.size"
        TEST_VALUE = "10"
        EXPECTED_VALUE = 10

        loader._set_nested_value(config, TEST_PATH, TEST_VALUE)

        assert (
            config["database"]["connection"]["pool"]["size"] == EXPECTED_VALUE
        )


class TestGetMethod:
    """Test the get method for retrieving config values."""

    def test__given_valid_existing_value__get_method_fetches_value(
        self, temp_default_config
    ):
        """Test getting an existing configuration value."""
        loader = ConfigLoader(default_config_path=temp_default_config)

        APP_NAME = loader.get("app.name")
        assert APP_NAME == DEFAULT_CONFIG_DATA["app"]["name"]

        DB_PROVIDER = loader.get("database.provider")
        assert DB_PROVIDER == DEFAULT_CONFIG_DATA["database"]["provider"]

    def test__given_deeply_nested_value__get_method_fetches_value(
        self, temp_default_config
    ):
        """Test getting a deeply nested configuration value."""
        loader = ConfigLoader(default_config_path=temp_default_config)

        SERVER_PORT = loader.get("server.port")
        assert SERVER_PORT == DEFAULT_CONFIG_DATA["server"]["port"]

    def test__given_nonexistent_value_with_default__get_method_returns_default(
        self, temp_default_config
    ):
        """Test getting a non-existent value returns the default."""
        loader = ConfigLoader(default_config_path=temp_default_config)

        DEFAULT_VALUE = "default-value"
        result = loader.get("non.existent.path", DEFAULT_VALUE)
        assert result == DEFAULT_VALUE

    def test__given_nonexistent_value_without_default__get_method_returns_none(
        self, temp_default_config
    ):
        """Test getting a non-existent value returns None when no default."""
        loader = ConfigLoader(default_config_path=temp_default_config)

        result = loader.get("non.existent.path")
        assert result is None

    def test__given_config_not_loaded__get_method_triggers_load(self):
        """Test that get() triggers load() if config not yet loaded."""
        loader = ConfigLoader(default_config_path="/non/existent/path")
        assert loader._config is None

        # This should trigger load()
        result = loader.get("some.path", "default")

        assert loader._config is not None  # Config should now be loaded
        assert result == "default"  # Path doesn't exist, should return default


class TestDeepMerge:
    """Test the deep merge functionality."""

    def test__given_non_overlapping_keys__deep_merge_correctly_merges(self):
        """Test merging dictionaries with non-overlapping keys."""
        loader = ConfigLoader()

        BASE = {"a": 1, "b": 2}
        OVERRIDE = {"c": 3, "d": 4}

        result = loader._deep_merge(BASE, OVERRIDE)

        assert result == {"a": 1, "b": 2, "c": 3, "d": 4}

    def test__given_overlapping_simple_keys__deep_merge_overwrites_values(
        self,
    ):
        """Test merging dictionaries with overlapping simple values."""
        loader = ConfigLoader()

        BASE = {"a": 1, "b": 2, "c": 3}
        OVERRIDE = {"b": 20, "c": 30, "d": 4}

        result = loader._deep_merge(BASE, OVERRIDE)

        assert result == {"a": 1, "b": 20, "c": 30, "d": 4}

    def test__given_nested_dicts__deep_merge_correctly_merges(self):
        """Test merging nested dictionaries."""
        loader = ConfigLoader()

        BASE = {
            "app": {"name": "base", "version": "1.0"},
            "db": {"host": "localhost", "port": 5432},
        }
        OVERRIDE = {
            "app": {"version": "2.0", "debug": True},
            "db": {"host": "remotehost"},
        }

        result = loader._deep_merge(BASE, OVERRIDE)

        assert result == {
            "app": {"name": "base", "version": "2.0", "debug": True},
            "db": {"host": "remotehost", "port": 5432},
        }

    def test__given_dict_values__deep_merge_dict_replaces_non_dict(self):
        """Test that dict values replace non-dict values entirely."""
        loader = ConfigLoader()

        BASE = {"a": "string_value", "b": {"nested": True}}
        OVERRIDE = {"a": {"new": "dict"}, "b": "string_value"}

        result = loader._deep_merge(BASE, OVERRIDE)

        assert result == {"a": {"new": "dict"}, "b": "string_value"}


class TestGlobalFunctions:
    """Test the global convenience functions."""

    def test__given_valid_config__get_config_function_returns_expected_values(
        self, temp_default_config, clean_env
    ):
        """Test the global get_config() function."""
        clean_env.setenv("CONFIG_FILE", temp_default_config)

        # Reset global instance for clean test
        from policyengine_household_api.utils import config_loader

        config_loader._config_loader = ConfigLoader(
            default_config_path=temp_default_config
        )

        config = get_config()
        assert config["app"]["name"] == DEFAULT_CONFIG_DATA["app"]["name"]

    def test__given_valid_config__get_config_value_function_returns_expected_value(
        self, temp_default_config, clean_env
    ):
        """Test the global get_config_value() function."""
        clean_env.setenv("CONFIG_FILE", temp_default_config)

        # Reset global instance for clean test
        from policyengine_household_api.utils import config_loader

        config_loader._config_loader = ConfigLoader(
            default_config_path=temp_default_config
        )

        app_name = get_config_value("app.name")
        assert app_name == DEFAULT_CONFIG_DATA["app"]["name"]

        default_value = get_config_value("non.existent", "default")
        assert default_value == "default"


class TestEnvironmentVariableSubstitution:
    """Test environment variable substitution in config files."""

    def test__given_config_with_env_var_syntax__substitution_occurs(
        self, tmp_path, clean_env
    ):
        """Test that ${VAR} syntax is replaced with environment variable values."""
        # Set environment variables
        clean_env.setenv("TEST_APP_NAME", "substituted-app-name")
        clean_env.setenv("TEST_DB_HOST", "substituted-db-host")
        clean_env.setenv("TEST_DB_PORT", "5432")

        # Create config with ${VAR} syntax
        config_data = {
            "app": {"name": "${TEST_APP_NAME}", "environment": "test"},
            "database": {"host": "${TEST_DB_HOST}", "port": "${TEST_DB_PORT}"},
        }

        config_file = tmp_path / "config_with_vars.yaml"
        config_file.write_text(yaml.dump(config_data))

        loader = ConfigLoader(default_config_path=str(config_file))
        config = loader.load()

        assert config["app"]["name"] == "substituted-app-name"
        assert config["database"]["host"] == "substituted-db-host"
        assert config["database"]["port"] == "5432"

    def test__given_config_with_dollar_var_syntax__substitution_occurs(
        self, tmp_path, clean_env
    ):
        """Test that $VAR syntax (without braces) is also replaced."""
        clean_env.setenv("TEST_VALUE", "replaced-value")

        config_data = {
            "setting": "$TEST_VALUE",
            "path": "/path/to/$TEST_VALUE/dir",
        }

        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump(config_data))

        loader = ConfigLoader(default_config_path=str(config_file))
        config = loader.load()

        assert config["setting"] == "replaced-value"
        assert config["path"] == "/path/to/replaced-value/dir"

    def test__given_undefined_env_var__original_syntax_preserved(
        self, tmp_path, clean_env
    ):
        """Test that undefined environment variables keep the original ${VAR} syntax."""
        config_data = {
            "undefined": "${UNDEFINED_VAR}",
            "mixed": "${UNDEFINED_VAR}/some/path",
        }

        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump(config_data))

        loader = ConfigLoader(default_config_path=str(config_file))
        config = loader.load()

        assert config["undefined"] == "${UNDEFINED_VAR}"
        assert config["mixed"] == "${UNDEFINED_VAR}/some/path"

    def test__given_nested_config_with_env_vars__substitution_occurs_at_all_levels(
        self, tmp_path, clean_env
    ):
        """Test that substitution works in nested dictionaries and lists."""
        clean_env.setenv("TEST_NESTED_VALUE", "nested-replaced")
        clean_env.setenv("TEST_LIST_ITEM", "list-replaced")

        config_data = {
            "level1": {"level2": {"level3": "${TEST_NESTED_VALUE}"}},
            "list_items": [
                "${TEST_LIST_ITEM}",
                "static-value",
                {"nested_in_list": "${TEST_NESTED_VALUE}"},
            ],
        }

        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump(config_data))

        loader = ConfigLoader(default_config_path=str(config_file))
        config = loader.load()

        assert config["level1"]["level2"]["level3"] == "nested-replaced"
        assert config["list_items"][0] == "list-replaced"
        assert config["list_items"][1] == "static-value"
        assert config["list_items"][2]["nested_in_list"] == "nested-replaced"

    def test__given_auth0_config_with_env_vars__substitution_enables_auth(
        self, tmp_path, clean_env
    ):
        """Test real-world scenario with Auth0 configuration."""
        # Set Auth0 environment variables
        clean_env.setenv("AUTH0_ADDRESS_NO_DOMAIN", "test.auth0.com")
        clean_env.setenv("AUTH0_AUDIENCE_NO_DOMAIN", "https://test-api")
        clean_env.setenv("AUTH0_TEST_TOKEN_NO_DOMAIN", "test-jwt-token")

        config_data = {
            "auth": {
                "enabled": True,
                "auth0": {
                    "address": "${AUTH0_ADDRESS_NO_DOMAIN}",
                    "audience": "${AUTH0_AUDIENCE_NO_DOMAIN}",
                    "test_token": "${AUTH0_TEST_TOKEN_NO_DOMAIN}",
                },
            }
        }

        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump(config_data))

        loader = ConfigLoader(default_config_path=str(config_file))
        config = loader.load()

        assert config["auth"]["enabled"] is True
        assert config["auth"]["auth0"]["address"] == "test.auth0.com"
        assert config["auth"]["auth0"]["audience"] == "https://test-api"
        assert config["auth"]["auth0"]["test_token"] == "test-jwt-token"

    def test__given_external_config_with_env_vars__substitution_occurs(
        self, tmp_path, clean_env
    ):
        """Test that substitution works in external config files too."""
        clean_env.setenv("EXTERNAL_VALUE", "external-replaced")

        # Create external config
        external_data = {"external_setting": "${EXTERNAL_VALUE}"}
        external_file = tmp_path / "external.yaml"
        external_file.write_text(yaml.dump(external_data))

        # Set CONFIG_FILE to point to external config
        clean_env.setenv("CONFIG_FILE", str(external_file))

        loader = ConfigLoader(default_config_path="/non/existent")
        config = loader.load()

        assert config["external_setting"] == "external-replaced"


class TestErrorHandling:
    """Test error handling in various scenarios."""

    def test__given_invalid_yaml_config__error_throws(
        self, temp_invalid_yaml_config, clean_env, caplog
    ):
        """Test handling of invalid YAML in config file."""
        with caplog.at_level(logging.ERROR):
            loader = ConfigLoader(default_config_path=temp_invalid_yaml_config)
            config = loader.load()

            assert config == {}  # Should return empty dict on error
            assert "Error parsing YAML in default config" in caplog.text

    def test__given_permission_error_reading_config__error_throws(
        self, tmp_path, clean_env, caplog
    ):
        """Test handling of permission errors when reading config."""
        # Create a file with no read permissions
        config_file = tmp_path / "no_read.yaml"
        config_file.write_text("test: data")
        config_file.chmod(0o000)

        try:
            with caplog.at_level(logging.ERROR):
                loader = ConfigLoader(default_config_path=str(config_file))
                config = loader.load()

                assert config == {}  # Should return empty dict on error
                assert (
                    "Permission denied reading default config" in caplog.text
                )
        finally:
            # Clean up - restore permissions for deletion
            config_file.chmod(0o644)

    def test__given_unexpected_loading_error__error_throws(
        self, tmp_path, clean_env, caplog
    ):
        """Test handling of unexpected errors during config loading."""
        # Create a real file so the path.exists() check passes
        config_file = tmp_path / "config.yaml"
        config_file.write_text("test: data")

        # Mock open to raise an unexpected error when trying to read this specific file
        with patch("builtins.open", side_effect=Exception("Unexpected error")):
            with caplog.at_level(logging.ERROR):
                loader = ConfigLoader(default_config_path=str(config_file))
                config = loader.load()

                assert config == {}
                assert "Unexpected error loading default config" in caplog.text


class TestConfigValueSettings:
    """Test CONFIG_VALUE_SETTINGS functionality."""

    def test__given_no_config_value_settings__uses_environment_variables(
        self, clean_env, temp_config_with_variables
    ):
        """Test that without CONFIG_VALUE_SETTINGS, it falls back to environment variables."""
        # Set up environment variable
        clean_env.setenv("TEST_VAR", "from_env")
        clean_env.setenv("AUTH0_ADDRESS", "from_env_auth")
        clean_env.setenv("AUTH0_AUDIENCE", "from_env_audience")
        clean_env.setenv("DB_PASSWORD", "from_env_password")
        clean_env.setenv("ANOTHER_VAR", "from_env_another")

        # Set CONFIG_FILE to use the config with variables
        clean_env.setenv("CONFIG_FILE", temp_config_with_variables)

        # Create loader and load config
        loader = ConfigLoader()
        config = loader.load()

        # Should use environment variables via os.path.expandvars
        assert config.get("auth", {}).get("address") == "from_env_auth"
        assert config.get("auth", {}).get("audience") == "from_env_audience"
        assert (
            config.get("database", {}).get("password") == "from_env_password"
        )
        assert config.get("special") == "from_env_another"

    def test__given_valid_config_values_file__substitutes_correctly(
        self,
        clean_env,
        temp_valid_config_values_file,
        temp_config_with_variables,
    ):
        """Test that valid config values file is loaded and used for substitution."""
        # Set up environment
        clean_env.setenv("CONFIG_FILE", temp_config_with_variables)
        clean_env.setenv(
            "CONFIG_VALUE_SETTINGS", temp_valid_config_values_file
        )

        # Load config
        loader = ConfigLoader()
        config = loader.load()

        # Verify substitutions
        assert config["auth"]["address"] == "example.auth0.com"
        assert (
            config["auth"]["audience"] == "https://api.example.com"
        )  # $VAR syntax
        assert config["database"]["password"] == "secret123"
        assert config["special"] == "value_with_equals=sign"

    def test__given_missing_variable_in_values_file__logs_warning(
        self,
        clean_env,
        temp_missing_vars_config_values,
        temp_config_with_missing_var,
        caplog,
    ):
        """Test that missing variables in values file generate warnings."""
        # Set up environment
        clean_env.setenv("CONFIG_FILE", temp_config_with_missing_var)
        clean_env.setenv(
            "CONFIG_VALUE_SETTINGS", temp_missing_vars_config_values
        )

        # Load config with logging
        with caplog.at_level(logging.WARNING):
            loader = ConfigLoader()
            config = loader.load()

        # Verify substitution and warning
        assert config["auth"]["address"] == "example.auth0.com"
        assert (
            config["auth"]["audience"] == "${MISSING_VAR}"
        )  # Not substituted
        assert (
            "Variable ${MISSING_VAR} not found in config values file"
            in caplog.text
        )

    def test__given_invalid_format_in_values_file__raises_error(
        self, clean_env, temp_invalid_format_values_file
    ):
        """Test that invalid format in values file raises descriptive error."""
        # Set up environment
        clean_env.setenv(
            "CONFIG_VALUE_SETTINGS", temp_invalid_format_values_file
        )

        # Load should raise error
        loader = ConfigLoader()
        with pytest.raises(ValueError) as exc_info:
            loader._load_config_values_file()

        assert "Invalid format" in str(exc_info.value)
        assert "line 2" in str(exc_info.value)
        assert "invalid-key=value" in str(exc_info.value)

    def test__given_invalid_key_starting_with_number__raises_error(
        self, clean_env, temp_invalid_key_number_values_file
    ):
        """Test that keys starting with numbers raise error."""
        clean_env.setenv(
            "CONFIG_VALUE_SETTINGS", temp_invalid_key_number_values_file
        )

        loader = ConfigLoader()
        with pytest.raises(ValueError) as exc_info:
            loader._load_config_values_file()

        assert "Invalid format" in str(exc_info.value)
        assert "123_KEY=value" in str(exc_info.value)

    def test__given_nonexistent_values_file__raises_descriptive_error(
        self, clean_env
    ):
        """Test that nonexistent values file raises descriptive error."""
        nonexistent_file = "/tmp/nonexistent_config_values.env"
        clean_env.setenv("CONFIG_VALUE_SETTINGS", nonexistent_file)

        loader = ConfigLoader()
        with pytest.raises(FileNotFoundError) as exc_info:
            loader._load_config_values_file()

        assert "Configuration values file not found" in str(exc_info.value)
        assert nonexistent_file in str(exc_info.value)
        assert (
            "Please ensure the file exists or unset CONFIG_VALUE_SETTINGS"
            in str(exc_info.value)
        )

    def test__given_no_permission_to_read_values_file__raises_descriptive_error(
        self, clean_env, temp_no_read_permission_values_file
    ):
        """Test that permission error on values file raises descriptive error."""
        clean_env.setenv(
            "CONFIG_VALUE_SETTINGS", temp_no_read_permission_values_file
        )

        loader = ConfigLoader()
        with pytest.raises(PermissionError) as exc_info:
            loader._load_config_values_file()

        assert "Cannot read configuration values file" in str(exc_info.value)
        assert "Please check file permissions" in str(exc_info.value)

    def test__given_duplicate_keys_in_values_file__uses_latest_value(
        self,
        clean_env,
        temp_duplicate_keys_values_file,
        temp_config_with_duplicate_key,
        caplog,
    ):
        """Test that duplicate keys use the latest value and log warning."""
        clean_env.setenv("CONFIG_FILE", temp_config_with_duplicate_key)
        clean_env.setenv(
            "CONFIG_VALUE_SETTINGS", temp_duplicate_keys_values_file
        )

        with caplog.at_level(logging.WARNING):
            loader = ConfigLoader()
            config = loader.load()

        # Should use the latest value
        assert config["test"] == "second_value"
        # Should log warning
        assert "Duplicate key 'DUPLICATE_KEY'" in caplog.text
        assert "line 3" in caplog.text

    def test__given_empty_values_file__works_correctly(
        self, clean_env, temp_empty_values_file
    ):
        """Test that empty values file works without error."""
        clean_env.setenv("CONFIG_VALUE_SETTINGS", temp_empty_values_file)

        loader = ConfigLoader()
        values = loader._load_config_values_file()

        assert values == {}

    def test__given_values_file_loaded_once__caches_result(
        self, clean_env, temp_valid_config_values_file
    ):
        """Test that config values file is only loaded once and cached."""
        clean_env.setenv(
            "CONFIG_VALUE_SETTINGS", temp_valid_config_values_file
        )

        loader = ConfigLoader()

        # First load
        values1 = loader._load_config_values_file()
        assert "AUTH0_ADDRESS" in values1

        # Second load should return cached result
        values2 = loader._load_config_values_file()
        assert values2 is values1  # Same object reference

    def test__given_complex_values__handles_correctly(
        self,
        clean_env,
        temp_complex_values_file,
        temp_config_with_complex_values,
    ):
        """Test that complex values with special characters are handled correctly."""
        clean_env.setenv("CONFIG_FILE", temp_config_with_complex_values)
        clean_env.setenv("CONFIG_VALUE_SETTINGS", temp_complex_values_file)

        loader = ConfigLoader()
        config = loader.load()

        assert config["url"] == "https://example.com?param=value&other=123"
        assert config["json"] == '{"key": "value", "number": 123}'
        assert config["path"] == "/path/to/some file.txt"
        assert config["empty"] == ""
        assert config["quoted"] == '"quoted value"'

    def test__integration_with_real_config_structure(
        self,
        clean_env,
        temp_realistic_values_file,
        temp_realistic_config_with_vars,
    ):
        """Test integration with real-world config structure."""
        clean_env.setenv("CONFIG_FILE", temp_realistic_config_with_vars)
        clean_env.setenv("CONFIG_VALUE_SETTINGS", temp_realistic_values_file)

        loader = ConfigLoader()
        config = loader.load()

        # Verify all substitutions
        assert (
            config["auth"]["auth0"]["address"] == "policyengine.uk.auth0.com"
        )
        assert (
            config["auth"]["auth0"]["audience"]
            == "https://household.api.policyengine.org"
        )
        assert config["auth"]["auth0"]["test_token"] == "test-jwt-token"
        assert (
            config["analytics"]["database"]["connection_name"]
            == "project:region:instance"
        )
        assert config["analytics"]["database"]["username"] == "analytics_user"
        assert config["analytics"]["database"]["password"] == "analytics_pass"

        # Verify non-substituted values remain
        assert config["app"]["name"] == "policyengine-household-api"
        assert config["auth"]["enabled"] == True
        assert config["analytics"]["enabled"] == True
