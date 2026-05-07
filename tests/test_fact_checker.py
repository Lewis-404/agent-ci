"""Tests for Fact Checker."""

import json
from pathlib import Path

import pytest

from agent_ci.checkers.fact import FactChecker
from agent_ci.types import Severity


@pytest.fixture
def checker():
    return FactChecker()


@pytest.mark.asyncio
async def test_file_existence_valid(valid_output, checker):
    """Verify file count for existing pattern."""
    config = {
        "fact": {
            "files": [
                {"pattern": "*.json", "expected_count": 1}
            ]
        }
    }
    checker = FactChecker(config=config)
    report = await checker.verify(valid_output)
    file_count = [c for c in report.checks if c.check_name == "fact:file_count"]
    assert any(c.severity == Severity.PASS for c in file_count)


@pytest.mark.asyncio
async def test_file_existence_mismatch(valid_output):
    """Verify wrong expected count triggers failure."""
    config = {
        "fact": {
            "files": [
                {"pattern": "*.json", "expected_count": 999}
            ]
        }
    }
    checker = FactChecker(config=config)
    report = await checker.verify(valid_output)
    file_count = [c for c in report.checks if c.check_name == "fact:file_count"]
    assert any(c.severity == Severity.FAIL for c in file_count)


@pytest.mark.asyncio
async def test_min_size_check(tmp_path):
    """Verify files below min size trigger warning."""
    (tmp_path / "tiny.json").write_text("{}")
    config = {
        "fact": {
            "files": [
                {"pattern": "*.json", "min_size_bytes": 100}
            ]
        }
    }
    checker = FactChecker(config=config)
    report = await checker.verify(tmp_path)
    size_checks = [c for c in report.checks if c.check_name == "fact:file_size"]
    assert any(c.severity == Severity.WARN for c in size_checks)


@pytest.mark.asyncio
async def test_content_contains(tmp_path):
    """Verify content contains check passes."""
    (tmp_path / "result.json").write_text(json.dumps({"status": "success"}))
    config = {
        "fact": {
            "files": [{
                "pattern": "result.json",
                "content_checks": [{"type": "contains", "value": "success"}]
            }]
        }
    }
    checker = FactChecker(config=config)
    report = await checker.verify(tmp_path)
    content = [c for c in report.checks if c.check_name == "fact:content_contains"]
    assert any(c.severity == Severity.PASS for c in content)


@pytest.mark.asyncio
async def test_content_contains_fail(tmp_path):
    """Verify missing content triggers failure."""
    (tmp_path / "result.json").write_text(json.dumps({"status": "error"}))
    config = {
        "fact": {
            "files": [{
                "pattern": "result.json",
                "content_checks": [{"type": "contains", "value": "nonexistent_value"}]
            }]
        }
    }
    checker = FactChecker(config=config)
    report = await checker.verify(tmp_path)
    content = [c for c in report.checks if c.check_name == "fact:content_contains"]
    assert any(c.severity == Severity.FAIL for c in content)


@pytest.mark.asyncio
async def test_content_not_contains(tmp_path):
    """Verify forbidden content triggers failure."""
    (tmp_path / "result.json").write_text(json.dumps({"error": "panic: null pointer"}))
    config = {
        "fact": {
            "files": [{
                "pattern": "result.json",
                "content_checks": [{"type": "not_contains", "value": "panic"}]
            }]
        }
    }
    checker = FactChecker(config=config)
    report = await checker.verify(tmp_path)
    content = [c for c in report.checks if c.check_name == "fact:content_not_contains"]
    assert any(c.severity == Severity.FAIL for c in content)


@pytest.mark.asyncio
async def test_api_check_skipped_no_endpoint(valid_output):
    """Empty API config should skip gracefully."""
    config = {"fact": {"api": [{}]}}
    checker = FactChecker(config=config)
    report = await checker.verify(valid_output)
    api_checks = [c for c in report.checks if c.check_name == "fact:api"]
    assert len(api_checks) == 1
    assert api_checks[0].severity == Severity.WARN


@pytest.mark.asyncio
async def test_api_check_success():
    """Verify API check against a real endpoint."""
    config = {
        "fact": {
            "api": [{
                "endpoint": "https://httpbin.org/get",
                "method": "GET",
                "expected_status": 200,
                "timeout": 10,
            }]
        }
    }
    checker = FactChecker(config=config)
    report = await checker.verify(Path("/tmp"))
    api_checks = [c for c in report.checks if c.check_name == "fact:api"]
    assert len(api_checks) == 1
    assert api_checks[0].severity == Severity.PASS


@pytest.mark.asyncio
async def test_api_check_timeout():
    """Verify timeout handling."""
    config = {
        "fact": {
            "api": [{
                "endpoint": "https://httpbin.org/delay/5",
                "method": "GET",
                "expected_status": 200,
                "timeout": 1,
            }]
        }
    }
    checker = FactChecker(config=config)
    report = await checker.verify(Path("/tmp"))
    api_checks = [c for c in report.checks if c.check_name == "fact:api"]
    assert len(api_checks) == 1
    assert api_checks[0].severity == Severity.FAIL
    assert "timeout" in api_checks[0].message.lower()


@pytest.mark.asyncio
async def test_llm_judge_no_file(valid_output):
    """LLM judge without file should warn."""
    config = {"fact": {"llm_judge": [{"rubric": "test"}]}}
    checker = FactChecker(config=config)
    report = await checker.verify(valid_output)
    judge = [c for c in report.checks if c.check_name == "fact:llm_judge"]
    assert len(judge) == 1
    assert judge[0].severity == Severity.WARN


@pytest.mark.asyncio
async def test_llm_judge_no_matching_files(valid_output):
    """LLM judge with non-matching pattern should fail."""
    config = {
        "fact": {
            "llm_judge": [{"file": "nonexistent_*.json", "rubric": "test"}]
        }
    }
    checker = FactChecker(config=config)
    report = await checker.verify(valid_output)
    judge = [c for c in report.checks if c.check_name == "fact:llm_judge"]
    assert len(judge) == 1
    assert judge[0].severity == Severity.FAIL


@pytest.mark.asyncio
async def test_llm_judge_no_llm_installed(valid_output):
    """LLM judge without openai/litellm should warn gracefully."""
    config = {
        "fact": {
            "llm_judge": [{"file": "result.json", "rubric": "Check correctness"}]
        }
    }
    checker = FactChecker(config=config)
    report = await checker.verify(valid_output)
    judge = [c for c in report.checks if c.check_name == "fact:llm_judge"]
    assert len(judge) >= 1
    # Should fail or warn since no LLM is installed
    assert judge[0].severity in (Severity.WARN, Severity.FAIL)
