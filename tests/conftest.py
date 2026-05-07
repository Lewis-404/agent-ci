"""Test fixtures and helpers."""

from pathlib import Path

import pytest


@pytest.fixture
def fixtures_dir() -> Path:
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def valid_output(fixtures_dir: Path) -> Path:
    return fixtures_dir / "valid_output"


@pytest.fixture
def invalid_output(fixtures_dir: Path) -> Path:
    return fixtures_dir / "invalid_output"


@pytest.fixture
def baseline_dir(fixtures_dir: Path) -> Path:
    return fixtures_dir / "baseline"


@pytest.fixture
def tmp_output(tmp_path: Path) -> Path:
    """Create a temporary output directory with test files."""
    import json

    (tmp_path / "valid.json").write_text(
        json.dumps({"status": "ok", "count": 10})
    )
    (tmp_path / "data.yaml").write_text("name: test\nversion: '1.0'\n")
    return tmp_path
