"""YAML configuration loader for agent-ci."""

from pathlib import Path
from typing import Any

import yaml


DEFAULT_CONFIG: dict[str, Any] = {
    "schema": {
        "json_schemas": {},
        "security": {"enabled": True},
        "required_files": [],
    },
    "fact": {
        "files": [],
        "api": [],
        "llm_judge": [],
    },
    "diff": {
        "baseline": None,
        "semantic_threshold": 0.7,
    },
    "pipeline": {
        "enabled_checkers": ["schema", "fact", "diff"],
        "fail_fast": False,
        "parallel": True,
    },
    "plugins": {
        "paths": [],
    },
}


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    """Load agent-ci config from YAML file, merging with defaults.

    Search order:
    1. Explicit path passed in
    2. .agent-ci.yaml in current directory
    3. .agent-ci.yaml in parent directories
    4. Return defaults

    Args:
        path: Optional explicit config file path.

    Returns:
        Merged configuration dict.
    """
    if path:
        config_path = Path(path)
        if not config_path.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")
        return _merge_with_defaults(_load_yaml(config_path))

    # Search upward for .agent-ci.yaml
    search_dir = Path.cwd()
    for _ in range(10):  # Max 10 levels up
        candidate = search_dir / ".agent-ci.yaml"
        if candidate.exists():
            return _merge_with_defaults(_load_yaml(candidate))
        if search_dir.parent == search_dir:
            break
        search_dir = search_dir.parent

    # No config found, use defaults
    return _deep_copy(DEFAULT_CONFIG)


def _load_yaml(path: Path) -> dict:
    """Load a YAML file."""
    with open(path) as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Config must be a mapping, got {type(data).__name__}")
    return data


def _deep_copy(d: dict) -> dict:
    """Simple deep copy via YAML round-trip."""
    return yaml.safe_load(yaml.dump(d))


def _merge_with_defaults(user_config: dict) -> dict:
    """Deep-merge user config into defaults. None values are skipped."""
    merged = _deep_copy(DEFAULT_CONFIG)

    def _merge(target: dict, source: dict) -> None:
        for key, value in source.items():
            if value is None:
                continue
            if key in target and isinstance(target[key], dict) and isinstance(value, dict):
                _merge(target[key], value)
            else:
                target[key] = value

    _merge(merged, user_config)
    return merged
