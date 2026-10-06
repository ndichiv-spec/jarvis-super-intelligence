"""
Centralized configuration loader with environment-aware resolution,
secret injection, type coercion, and validation.
"""

import os
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Type, Union, Callable
from dataclasses import dataclass, field
from enum import Enum


class ConfigValidationError(Exception):
    """Raised when configuration validation fails."""
    pass


class DeploymentEnvironment(Enum):
    LOCAL = "local"
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"
    TEST = "test"


@dataclass
class ConfigSource:
    """Represents a single configuration source with priority."""
    name: str
    priority: int
    loader: Callable[[], Dict[str, Any]]


@dataclass
class ConfigRule:
    """Validation rule for a config key."""
    key: str
    required: bool = False
    default: Any = None
    type_: Optional[Type] = None
    choices: Optional[List[str]] = None
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    pattern: Optional[str] = None
    description: str = ""
    sensitive: bool = False
    depends_on: Optional[List[str]] = None


class ConfigLoader:
    """
    Multi-source configuration loader with priority layering.

    Source priority (lowest number = highest priority):
      1. Environment variables (runtime)
      2. .env file (project root)
      3. .env.{environment} file
      4. Config file (JSON/YAML)
      5. Default values
    """

    def __init__(
        self,
        env_prefix: str = "JARVIS_",
        config_dir: Optional[Path] = None,
        environment: Optional[str] = None,
    ):
        self.env_prefix = env_prefix
        self.config_dir = config_dir or Path.cwd()
        self.environment = environment or os.getenv("JARVIS_ENV", "development")
        self.sources: List[ConfigSource] = []
        self.rules: Dict[str, ConfigRule] = {}
        self._resolved: Dict[str, Any] = {}
        self._resolved_sensitive: Set[str] = set()

    def add_source(self, name: str, priority: int, loader: Callable[[], Dict[str, Any]]):
        self.sources.append(ConfigSource(name=name, priority=priority, loader=loader))
        self.sources.sort(key=lambda s: s.priority)
        return self

    def add_rule(self, rule: ConfigRule):
        self.rules[rule.key] = rule
        return self

    def add_rules(self, rules: List[ConfigRule]):
        for rule in rules:
            self.add_rule(rule)
        return self

    def load(self) -> Dict[str, Any]:
        """Load and resolve configuration from all sources."""
        merged: Dict[str, Any] = {}

        # Load from sources in priority order (lowest first = highest priority)
        for source in self.sources:
            try:
                data = source.loader()
                merged.update(data)
            except Exception as e:
                if self.environment == DeploymentEnvironment.PRODUCTION.value:
                    raise ConfigValidationError(f"Config source '{source.name}' failed: {e}")
                continue

        # Apply defaults from rules
        for key, rule in self.rules.items():
            if key not in merged and rule.default is not None:
                merged[key] = rule.default

        # Validate
        self._validate(merged)

        # Type coerce
        merged = self._coerce_types(merged)

        self._resolved = merged
        return merged

    def _validate(self, config: Dict[str, Any]):
        """Validate configuration against defined rules."""
        errors: List[str] = []

        for key, rule in self.rules.items():
            value = config.get(key)

            # Required check
            if rule.required and value is None:
                errors.append(f"Missing required config: {key} - {rule.description}")
                continue

            if value is None:
                continue

            # Type check
            if rule.type_ and not isinstance(value, rule.type_):
                try:
                    rule.type_(value)
                except (TypeError, ValueError):
                    errors.append(
                        f"Config '{key}' should be {rule.type_.__name__}, got {type(value).__name__}"
                    )

            # Choices check
            if rule.choices and str(value) not in rule.choices:
                errors.append(
                    f"Config '{key}' must be one of {rule.choices}, got '{value}'"
                )

            # Range check
            if rule.min_value is not None and isinstance(value, (int, float)):
                if value < rule.min_value:
                    errors.append(f"Config '{key}' must be >= {rule.min_value}, got {value}")
            if rule.max_value is not None and isinstance(value, (int, float)):
                if value > rule.max_value:
                    errors.append(f"Config '{key}' must be <= {rule.max_value}, got {value}")

            # Pattern check
            if rule.pattern and isinstance(value, str):
                if not re.match(rule.pattern, value):
                    errors.append(f"Config '{key}' does not match pattern {rule.pattern}")

            # Dependency check
            if rule.depends_on:
                for dep in rule.depends_on:
                    if dep not in config or config[dep] is None:
                        errors.append(f"Config '{key}' depends on '{dep}' which is not set")

        if errors:
            raise ConfigValidationError(
                "Configuration validation failed:\n  " + "\n  ".join(errors)
            )

    def _coerce_types(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Coerce configuration values to their declared types."""
        coerced = dict(config)
        for key, rule in self.rules.items():
            if key not in coerced or coerced[key] is None:
                continue
            if rule.type_ and not isinstance(coerced[key], rule.type_):
                try:
                    coerced[key] = rule.type_(coerced[key])
                except (TypeError, ValueError):
                    pass
        return coerced

    def get(self, key: str, default: Any = None) -> Any:
        return self._resolved.get(key, default)

    def get_int(self, key: str, default: int = 0) -> int:
        return int(self._resolved.get(key, default))

    def get_bool(self, key: str, default: bool = False) -> bool:
        val = self._resolved.get(key, default)
        if isinstance(val, bool):
            return val
        return str(val).lower() in ("1", "true", "yes", "on")

    def get_list(self, key: str, default: Optional[List[str]] = None) -> List[str]:
        val = self._resolved.get(key, default)
        if isinstance(val, list):
            return val
        if isinstance(val, str):
            return [v.strip() for v in val.split(",") if v.strip()]
        return default or []

    def is_sensitive(self, key: str) -> bool:
        return self.rules.get(key, None) is not None and self.rules[key].sensitive

    def expose(self) -> Dict[str, Any]:
        """Expose non-sensitive config (safe for logging/debug endpoints)."""
        return {
            k: "***REDACTED***" if self.is_sensitive(k) else v
            for k, v in self._resolved.items()
        }


# Pre-built source loaders

def env_source(prefix: str = "") -> Callable[[], Dict[str, Any]]:
    """Load configuration from environment variables."""
    def loader() -> Dict[str, Any]:
        config: Dict[str, Any] = {}
        for key, value in os.environ.items():
            if prefix and not key.startswith(prefix):
                continue
            config_key = key[len(prefix):] if prefix else key
            config_key = config_key.lower().replace("__", ".")
            config[config_key] = value
        return config
    return loader


def dotenv_source(env_path: Optional[Path] = None) -> Callable[[], Dict[str, Any]]:
    """Load configuration from a .env file."""
    def loader() -> Dict[str, Any]:
        path = env_path or Path.cwd() / ".env"
        if not path.exists():
            return {}
        config: Dict[str, Any] = {}
        with open(path, "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip().lower()
                value = value.strip().strip("'\"").strip()
                if value:
                    config[key] = value
        return config
    return loader


def json_source(config_path: Path) -> Callable[[], Dict[str, Any]]:
    """Load configuration from a JSON file."""
    def loader() -> Dict[str, Any]:
        if not config_path.exists():
            return {}
        with open(config_path, "r") as f:
            return json.load(f)
    return loader


def default_config_loader(environment: Optional[str] = None) -> ConfigLoader:
    """Create a pre-configured ConfigLoader with standard sources."""
    env = environment or os.getenv("JARVIS_ENV", "development")
    loader = ConfigLoader(env_prefix="JARVIS_", environment=env)

    loader.add_source("defaults", 100, lambda: {})
    loader.add_source("dotenv", 80, dotenv_source(Path.cwd() / ".env"))
    loader.add_source("dotenv_env", 75, dotenv_source(Path.cwd() / f".env.{env}"))
    loader.add_source("environment", 10, env_source("JARVIS_"))

    return loader
