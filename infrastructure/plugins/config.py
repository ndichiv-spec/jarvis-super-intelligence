"""
Per-plugin configuration management.

Provides:
  - JSON-based config storage per plugin
  - Schema validation on save
  - Default values from manifest schema
"""

from __future__ import annotations
import os
import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class PluginConfigError(Exception):
    pass


class PluginConfigManager:
    """
    Manages configuration files for individual plugins.

    Configs are stored as JSON files in a config directory:
        config/plugins/<plugin_id>.json
    """

    def __init__(self, config_dir: Optional[Path] = None):
        self.config_dir = config_dir or Path("config/plugins")
        self.config_dir.mkdir(parents=True, exist_ok=True)

    def load(self, plugin_id: str) -> Dict[str, Any]:
        config_file = self._path(plugin_id)
        if config_file.exists():
            try:
                with open(config_file, "r") as f:
                    data = json.load(f)
                logger.debug(f"Loaded config for plugin '{plugin_id}'")
                return data
            except json.JSONDecodeError as e:
                logger.warning(f"Invalid config for '{plugin_id}': {e}")
                return {}
        return {}

    def save(self, plugin_id: str, config: Dict[str, Any],
             schema: Optional[Dict[str, Any]] = None):
        if schema:
            self._validate(config, schema)
        config_file = self._path(plugin_id)
        config_file.parent.mkdir(parents=True, exist_ok=True)
        with open(config_file, "w") as f:
            json.dump(config, f, indent=2)
        logger.info(f"Saved config for plugin '{plugin_id}'")

    def delete(self, plugin_id: str):
        config_file = self._path(plugin_id)
        if config_file.exists():
            config_file.unlink()
            logger.info(f"Deleted config for plugin '{plugin_id}'")

    def get(self, plugin_id: str, key: str, default: Any = None) -> Any:
        config = self.load(plugin_id)
        return config.get(key, default)

    def set(self, plugin_id: str, key: str, value: Any):
        config = self.load(plugin_id)
        config[key] = value
        self.save(plugin_id, config)

    def list_plugins(self) -> list:
        return [
            f.stem for f in self.config_dir.glob("*.json")
        ]

    def _path(self, plugin_id: str) -> Path:
        return self.config_dir / f"{plugin_id}.json"

    def _validate(self, config: Dict[str, Any], schema: Dict[str, Any]):
        if not schema:
            return
        for key, rules in schema.items():
            if rules.get("required", False) and key not in config:
                raise PluginConfigError(f"Missing required config key: {key}")
            if key in config:
                expected_type = rules.get("type")
                if expected_type:
                    type_map = {
                        "string": str, "number": (int, float),
                        "integer": int, "boolean": bool, "array": list, "object": dict,
                    }
                    py_type = type_map.get(expected_type)
                    if py_type and not isinstance(config[key], py_type):
                        raise PluginConfigError(
                            f"Config '{key}' should be {expected_type}, got {type(config[key]).__name__}"
                        )
