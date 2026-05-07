"""Plugin discovery and loading for custom checkers.

Supports two modes:
1. Python entry points (group: agent_ci.checkers)
2. Directory-based: any .py file in a plugins/ directory exporting a checker class
"""

import importlib
import importlib.util
import sys
from pathlib import Path
from typing import Any

from agent_ci.checkers import BaseChecker


def discover_plugins(config: dict[str, Any]) -> dict[str, type[BaseChecker]]:
    """Discover all available plugins from config and entry points.

    Returns:
        Dict mapping checker name to checker class.
    """
    plugins: dict[str, type[BaseChecker]] = {}

    # 1. Entry points (pip-installed plugins)
    _load_entry_points(plugins)

    # 2. Directory-based plugins from config
    plugin_dirs = config.get("plugins", {}).get("paths", [])
    for path_str in plugin_dirs:
        _load_directory_plugins(Path(path_str), plugins)

    return plugins


def _load_entry_points(plugins: dict[str, type[BaseChecker]]) -> None:
    """Load checkers registered via setuptools entry points."""
    from importlib.metadata import entry_points

    try:
        eps = entry_points(group="agent_ci.checkers")
        for ep in eps:
            try:
                cls = ep.load()
                if issubclass(cls, BaseChecker) and hasattr(cls, "name"):
                    plugins[cls.name] = cls
            except Exception:
                pass
    except Exception:
        pass


def _load_directory_plugins(
    directory: Path, plugins: dict[str, type[BaseChecker]]
) -> None:
    """Load checker classes from .py files in a directory.

    Each .py file should export exactly one BaseChecker subclass.
    The class is registered by its `.name` attribute.
    """
    if not directory.exists() or not directory.is_dir():
        return

    for py_file in sorted(directory.glob("*.py")):
        if py_file.name.startswith("_"):
            continue
        try:
            module_name = f"_plugin_{py_file.stem}"
            spec = importlib.util.spec_from_file_location(module_name, py_file)
            if spec is None or spec.loader is None:
                continue
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)

            # Find BaseChecker subclass
            for attr_name in dir(module):
                obj = getattr(module, attr_name)
                if (
                    isinstance(obj, type)
                    and issubclass(obj, BaseChecker)
                    and obj is not BaseChecker
                    and hasattr(obj, "name")
                ):
                    plugins[obj.name] = obj
        except Exception:
            pass
