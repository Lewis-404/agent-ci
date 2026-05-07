"""Tests for Schema Checker."""

import json

import pytest

from agent_ci.checkers.schema import SchemaChecker
from agent_ci.types import Severity


@pytest.fixture
def checker():
    return SchemaChecker()


@pytest.mark.asyncio
async def test_valid_json(checker, valid_output):
    report = await checker.verify(valid_output)
    json_checks = [c for c in report.checks if c.check_name == "json_valid"]
    assert all(c.severity == Severity.PASS for c in json_checks)


@pytest.mark.asyncio
async def test_invalid_json(checker, invalid_output):
    report = await checker.verify(invalid_output)
    broken = [c for c in report.checks
              if c.check_name == "json_valid" and c.severity == Severity.FAIL]
    assert len(broken) == 1
    assert "broken.json" in broken[0].message


@pytest.mark.asyncio
async def test_valid_yaml(checker, valid_output):
    report = await checker.verify(valid_output)
    yaml_checks = [c for c in report.checks if c.check_name == "yaml_valid"]
    assert all(c.severity == Severity.PASS for c in yaml_checks)


@pytest.mark.asyncio
async def test_secret_detection(checker, invalid_output):
    report = await checker.verify(invalid_output)
    secret_checks = [c for c in report.checks
                     if c.check_name.startswith("secret:")]
    assert len(secret_checks) >= 1
    assert secret_checks[0].severity == Severity.FAIL
    assert "openai_key" in secret_checks[0].check_name


@pytest.mark.asyncio
async def test_no_secrets_in_clean_output(checker, valid_output):
    report = await checker.verify(valid_output)
    secret_checks = [c for c in report.checks if c.check_name == "security_scan"]
    assert len(secret_checks) == 1
    assert secret_checks[0].severity == Severity.PASS
    assert "No secrets" in secret_checks[0].message


@pytest.mark.asyncio
async def test_security_disabled(tmp_path):
    config = {"schema": {"security": {"enabled": False}}}
    checker = SchemaChecker(config=config)
    report = await checker.verify(tmp_path)
    secret_checks = [c for c in report.checks if "secret" in c.check_name.lower()]
    assert len(secret_checks) == 0


@pytest.mark.asyncio
async def test_required_files_present(tmp_path):
    (tmp_path / "required.txt").write_text("hello")
    config = {"schema": {"required_files": ["required.txt"]}}
    checker = SchemaChecker(config=config)
    report = await checker.verify(tmp_path)
    req = [c for c in report.checks if c.check_name == "required_file"]
    assert any(c.severity == Severity.PASS for c in req)


@pytest.mark.asyncio
async def test_required_files_missing(tmp_path):
    config = {"schema": {"required_files": ["nonexistent.txt"]}}
    checker = SchemaChecker(config=config)
    report = await checker.verify(tmp_path)
    req = [c for c in report.checks if c.check_name == "required_file"]
    assert any(c.severity == Severity.FAIL for c in req)


@pytest.mark.asyncio
async def test_schema_compliance(tmp_path):
    """Test that JSON schema validation works."""
    (tmp_path / "valid.json").write_text(json.dumps({"status": "ok", "count": 10}))
    schema = {
        "type": "object",
        "properties": {
            "status": {"type": "string"},
            "count": {"type": "integer"},
        },
        "required": ["status", "count"],
    }
    schema_path = tmp_path / "schema.json"
    schema_path.write_text(json.dumps(schema))

    config = {
        "schema": {
            "json_schemas": {str(schema_path): "valid.json"}
        }
    }
    checker = SchemaChecker(config=config)
    report = await checker.verify(tmp_path)
    compliance = [c for c in report.checks if c.check_name == "schema_compliance"]
    assert len(compliance) == 1
    assert compliance[0].severity == Severity.PASS


@pytest.mark.asyncio
async def test_schema_violation(tmp_path):
    """Test that schema violations are caught."""
    (tmp_path / "bad.json").write_text(json.dumps({"status": 123}))  # status should be string
    schema = {
        "type": "object",
        "properties": {"status": {"type": "string"}},
    }
    schema_path = tmp_path / "schema.json"
    schema_path.write_text(json.dumps(schema))

    config = {
        "schema": {
            "json_schemas": {str(schema_path): "bad.json"}
        }
    }
    checker = SchemaChecker(config=config)
    report = await checker.verify(tmp_path)
    compliance = [c for c in report.checks if c.check_name == "schema_compliance"]
    assert len(compliance) == 1
    assert compliance[0].severity in (Severity.FAIL, Severity.WARN)
