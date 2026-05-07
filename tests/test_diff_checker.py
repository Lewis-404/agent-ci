"""Tests for Diff Checker."""

import json
from pathlib import Path

import pytest

from agent_ci.checkers.diff import DiffChecker
from agent_ci.types import Severity


@pytest.fixture
def diff_config(baseline_dir: Path) -> dict:
    return {"diff": {"baseline": str(baseline_dir)}}


@pytest.mark.asyncio
async def test_diff_identical(valid_output, diff_config):
    """Files matching baseline should show no changes."""
    checker = DiffChecker(config=diff_config)
    report = await checker.verify(valid_output)
    changed = [c for c in report.checks if c.check_name == "diff:changed"]
    # result.json and summary.md match baseline exactly
    assert all(c.severity == Severity.PASS for c in changed)


@pytest.mark.asyncio
async def test_diff_new_file(valid_output, diff_config, baseline_dir):
    """New files not in baseline should be flagged."""
    checker = DiffChecker(config=diff_config)
    report = await checker.verify(valid_output)
    added = [c for c in report.checks if c.check_name == "diff:added"]
    # config.yaml is new
    assert len(added) >= 1
    assert any("config.yaml" in c.message for c in added)


@pytest.mark.asyncio
async def test_diff_removed_file(tmp_path, diff_config):
    """Files in baseline but missing from output should be flagged."""
    # Copy baseline files to tmp_path, then remove one
    import os
    import shutil
    baseline_dir = Path(diff_config["diff"]["baseline"])
    for f in baseline_dir.iterdir():
        shutil.copy2(f, tmp_path / f.name)
    os.remove(tmp_path / "summary.md")

    checker = DiffChecker(config=diff_config)
    report = await checker.verify(tmp_path)
    removed = [c for c in report.checks if c.check_name == "diff:removed"]
    assert len(removed) >= 1
    assert any("summary.md" in c.message for c in removed)


@pytest.mark.asyncio
async def test_diff_changed_file(tmp_path, diff_config):
    """Modified files should be detected with similarity score."""
    import shutil
    baseline_dir = Path(diff_config["diff"]["baseline"])
    for f in baseline_dir.iterdir():
        shutil.copy2(f, tmp_path / f.name)

    # Drastically change result.json
    (tmp_path / "result.json").write_text(
        json.dumps({"completely": "different", "content": ["x"] * 100})
    )

    checker = DiffChecker(config=diff_config)
    report = await checker.verify(tmp_path)
    changed = [c for c in report.checks if c.check_name == "diff:changed"]
    assert len(changed) >= 1
    result_change = [c for c in changed if "result.json" in c.message]
    assert len(result_change) == 1
    assert result_change[0].severity == Severity.FAIL  # drastic change
    assert "similarity" in result_change[0].message.lower()


@pytest.mark.asyncio
async def test_diff_no_baseline(valid_output):
    """Without baseline, diff checker should warn and skip."""
    checker = DiffChecker()
    report = await checker.verify(valid_output)
    assert report.worst_severity == Severity.WARN
    assert any("No baseline" in c.message for c in report.checks)


@pytest.mark.asyncio
async def test_diff_baseline_not_found(valid_output):
    """Non-existent baseline directory should fail."""
    config = {"diff": {"baseline": "/nonexistent/path"}}
    checker = DiffChecker(config=config)
    report = await checker.verify(valid_output)
    assert report.worst_severity == Severity.FAIL


@pytest.mark.asyncio
async def test_text_similarity():
    """Test Jaccard similarity calculation."""
    assert DiffChecker._text_similarity("hello world", "hello world") == 1.0
    assert DiffChecker._text_similarity("hello world", "goodbye universe") < 0.5
    assert DiffChecker._text_similarity("", "") == 1.0
    assert DiffChecker._text_similarity("hello", "") == 0.0


@pytest.mark.asyncio
async def test_max_changed_threshold(tmp_path, diff_config):
    """When changed files exceed max, should flag failure."""
    import shutil
    baseline_dir = Path(diff_config["diff"]["baseline"])
    for f in baseline_dir.iterdir():
        shutil.copy2(f, tmp_path / f.name)

    # Modify both files
    (tmp_path / "result.json").write_text("modified")
    (tmp_path / "summary.md").write_text("also modified")

    config = {"diff": {**diff_config["diff"], "max_changed_files": 1}}
    checker = DiffChecker(config=config)
    report = await checker.verify(tmp_path)
    threshold = [c for c in report.checks if c.check_name == "diff:threshold"]
    assert len(threshold) == 1
    assert threshold[0].severity == Severity.FAIL
