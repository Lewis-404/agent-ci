"""Checkers package — verification checkers for agent outputs."""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from agent_ci.types import CheckerReport


class BaseChecker(ABC):
    """Abstract base for all verification checkers."""

    name: str = "base"

    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}

    @abstractmethod
    async def verify(self, output_dir: Path) -> CheckerReport:
        """Run all checks against the given output directory."""
        ...

    def _resolve_path(self, output_dir: Path, pattern: str) -> list[Path]:
        """Glob-resolve a pattern relative to output_dir."""
        return sorted(output_dir.glob(pattern))


__all__ = ["BaseChecker"]
