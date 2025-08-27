"""
Configuration loader for PolicyEngine Household API.

Loads configuration with the following priority (highest to lowest):
1. Environment variables (override everything)
2. Mounted config file (if provided via CONFIG_FILE env var)
3. Default config baked into image
"""

import os
import yaml
from pathlib import Path
from typing import Any, Dict, Optional
import logging

logger = logging.getLogger(__name__)


class ConfigLoader:
    """
    Loads and merges configuration from multiple sources.

    Priority order (highest wins):
    1. Environment variables
    2. External config file (if CONFIG_FILE is set)
    3. Default config file baked into image
    """

    # Default location for baked-in config
    DEFAULT_CONFIG_PATH = "/app/config/default.yaml"

    # Environment variable to specify external config
    CONFIG_FILE_ENV_VAR = "CONFIG_FILE"

    # Mapping of environment variables to config paths
    # Format: "ENV_VAR_NAME": "config.path.to.value"
    ENV_VAR_MAPPING = {
        # Flask settings
        "FLASK_DEBUG": "app.debug",
        # Analytics database settings (for user analytics)
        "USER_ANALYTICS_DB_CONNECTION_NAME": "analytics.database.connection_name",
        "USER_ANALYTICS_DB_USERNAME": "analytics.database.username",
        "USER_ANALYTICS_DB_PASSWORD": "analytics.database.password",
        # Auth0 settings
        "AUTH0_ADDRESS_NO_DOMAIN": "auth.auth0.address",
        "AUTH0_AUDIENCE_NO_DOMAIN": "auth.auth0.audience",
        # AI settings
        "ANTHROPIC_API_KEY": "ai.anthropic.api_key",
        # Server settings
        "PORT": "server.port",
    }

    def __init__(self, default_config_path: Optional[str] = None):
        """
        Initialize the config loader.

        Args:
            default_config_path: Override the default config file location
        """
        self.default_config_path = (
            default_config_path or self.DEFAULT_CONFIG_PATH
        )
        self._config: Optional[Dict[str, Any]] = None

    def load(self) -> Dict[str, Any]:
        """
        Load and merge configuration from all sources.

        Returns:
            Merged configuration dictionary
        """
        if self._config is not None:
            return self._config

        # Start with empty config
        config = {}

        # 1. Load default config (lowest priority)
        default_config = self._load_default_config()
        if default_config:
            config = self._deep_merge(config, default_config)
            logger.info(
                f"Loaded default config from {self.default_config_path}"
            )

        # 2. Load external config file if specified
        external_config = self._load_external_config()
        if external_config:
            config = self._deep_merge(config, external_config)
            logger.info(
                f"Loaded external config from {os.getenv(self.CONFIG_FILE_ENV_VAR)}"
            )

        # 3. Override with environment variables (highest priority)
        env_overrides = self._load_env_overrides()
        if env_overrides:
            config = self._deep_merge(config, env_overrides)
            logger.info("Applied environment variable overrides")

        self._config = config
        return config

    def _load_default_config(self) -> Optional[Dict[str, Any]]:
        """Load the default config file baked into the image."""
        path = Path(self.default_config_path)
        if not path.exists():
            # It's acceptable for default config not to exist - just use empty dict
            logger.debug(
                f"Default config not found at {self.default_config_path}, using empty configuration"
            )
            return {}

        try:
            with open(path, "r") as f:
                content = yaml.safe_load(f)
                return content if content is not None else {}
        except yaml.YAMLError as e:
            logger.error(
                f"Error parsing YAML in default config at {self.default_config_path}: {e}"
            )
            # For YAML errors, return empty dict but log the error
            return {}
        except PermissionError as e:
            logger.error(
                f"Permission denied reading default config at {self.default_config_path}: {e}"
            )
            # For permission errors, return empty dict but log the error
            return {}
        except Exception as e:
            logger.error(
                f"Unexpected error loading default config at {self.default_config_path}: {e}"
            )
            # For unexpected errors, return empty dict but log the error
            return {}

    def _load_external_config(self) -> Optional[Dict[str, Any]]:
        """Load external config file if CONFIG_FILE env var is set."""
        config_file = os.getenv(self.CONFIG_FILE_ENV_VAR)
        if not config_file:
            return None

        path = Path(config_file)
        if not path.exists():
            logger.warning(
                f"External config file specified but not found: {config_file}"
            )
            return None

        try:
            with open(path, "r") as f:
                content = yaml.safe_load(f)
                if content is None:
                    logger.debug(
                        f"External config file {config_file} is empty"
                    )
                    return {}
                return content
        except yaml.YAMLError as e:
            logger.error(
                f"Error parsing YAML in external config at {config_file}: {e}"
            )
            return None
        except PermissionError as e:
            logger.error(
                f"Permission denied reading external config at {config_file}: {e}"
            )
            return None
        except Exception as e:
            logger.error(
                f"Unexpected error loading external config from {config_file}: {e}"
            )
            return None

    def _load_env_overrides(self) -> Dict[str, Any]:
        """
        Load configuration overrides from environment variables.

        Supports two methods:
        1. Explicit mapping (ENV_VAR_MAPPING)
        2. Double underscore notation (DATABASE__HOST -> database.host)
        """
        overrides = {}

        # Process explicitly mapped environment variables
        for env_var, config_path in self.ENV_VAR_MAPPING.items():
            value = os.getenv(env_var)
            if value is not None:
                self._set_nested_value(overrides, config_path, value)

        # Process double-underscore notation env vars
        # Format: SECTION__KEY__SUBKEY -> section.key.subkey
        for key, value in os.environ.items():
            if "__" in key and key not in self.ENV_VAR_MAPPING:
                # Skip system environment variables (those starting with underscores)
                if key.startswith("_"):
                    continue

                # Convert to lowercase and split
                path_parts = key.lower().split("__")

                # Skip if any part is empty (e.g., from vars starting/ending with __)
                if any(not part for part in path_parts):
                    continue

                config_path = ".".join(path_parts)
                self._set_nested_value(overrides, config_path, value)

        return overrides

    def _set_nested_value(
        self, d: Dict[str, Any], path: str, value: Any
    ) -> None:
        """
        Set a nested value in a dictionary using dot notation.

        Args:
            d: Dictionary to modify
            path: Dot-separated path (e.g., "database.host")
            value: Value to set
        """
        keys = path.split(".")
        current = d

        for key in keys[:-1]:
            if key not in current:
                current[key] = {}
            current = current[key]

        # Convert string values to appropriate types
        current[keys[-1]] = self._convert_value(value)

    def _convert_value(self, value: str) -> Any:
        """
        Convert string values to appropriate Python types.

        Args:
            value: String value from environment variable

        Returns:
            Converted value (bool, int, float, or original string)
        """
        if value.lower() in ("true", "yes", "1"):
            return True
        if value.lower() in ("false", "no", "0"):
            return False

        try:
            return int(value)
        except ValueError:
            pass

        try:
            return float(value)
        except ValueError:
            pass

        return value

    def _deep_merge(
        self, base: Dict[str, Any], override: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Deep merge two dictionaries, with override taking precedence.

        Args:
            base: Base dictionary
            override: Dictionary with values to override

        Returns:
            Merged dictionary
        """
        result = base.copy()

        for key, value in override.items():
            if (
                key in result
                and isinstance(result[key], dict)
                and isinstance(value, dict)
            ):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value

        return result

    def get(self, path: str, default: Any = None) -> Any:
        """
        Get a configuration value using dot notation.

        Args:
            path: Dot-separated path (e.g., "database.host")
            default: Default value if path not found

        Returns:
            Configuration value or default
        """
        if self._config is None:
            self.load()

        keys = path.split(".")
        current = self._config

        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return default

        return current


# Global instance for convenience
_config_loader = ConfigLoader()


def get_config() -> Dict[str, Any]:
    """Get the loaded configuration."""
    return _config_loader.load()


def get_config_value(path: str, default: Any = None) -> Any:
    """Get a specific configuration value."""
    return _config_loader.get(path, default)
