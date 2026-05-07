"""Schema Checker — validates output file formats, structure, and security."""

import json
import re
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft7Validator, ValidationError as JsonSchemaError

from agent_ci.checkers.base import BaseChecker
from agent_ci.types import CheckResult, CheckerReport, Severity

# ── Security patterns ──────────────────────────────────────────────
_SECRET_PATTERNS: list[tuple[str, str, str]] = [
    # (name, pattern, description)
    ("aws_access_key", r"AKIA[0-9A-Z]{16}", "AWS Access Key ID"),
    ("github_token", r"gh[pousr]_[A-Za-z0-9_]{36,}", "GitHub Personal Access Token"),
    ("openai_key", r"sk-(?:proj-)?[A-Za-z0-9_-]{32,}", "OpenAI API Key"),
    ("jwt_token", r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}", "JWT Token"),
    ("private_key", r"-----BEGIN (RSA|EC|DSA|OPENSSH) PRIVATE KEY-----", "Private Key"),
    ("generic_password", r'(?:password|passwd|pwd|secret)\s*[:=]\s*["\'][^\s"\']{8,}["\']', "Password/Secret assignment"),
]


class SchemaChecker(BaseChecker):
    """Validates output file formats, JSON/YAML schema compliance, and security."""

    name = "schema"

    async def verify(self, output_dir: Path) -> CheckerReport:
        report = CheckerReport(checker_name=self.name)
        files = list(output_dir.rglob("*"))
        config = self.config.get("schema", {})

        # 1. Validate JSON files
        json_files = [f for f in files if f.suffix in (".json",)]
        for fpath in json_files:
            report.checks.extend(self._validate_json(fpath))

        # 2. Validate YAML files
        yaml_files = [f for f in files if f.suffix in (".yaml", ".yml")]
        for fpath in yaml_files:
            report.checks.extend(self._validate_yaml(fpath))

        # 3. Schema compliance (if schemas provided)
        schemas = config.get("json_schemas") or {}
        for schema_path, file_pattern in schemas.items():
            schema = self._load_schema(Path(schema_path))
            if schema is None:
                continue
            for fpath in output_dir.glob(file_pattern):
                report.checks.append(self._check_schema_compliance(fpath, schema))

        # 4. Security scan (API keys, tokens, etc.)
        sec_config = config.get("security", {})
        if sec_config.get("enabled", True):
            report.checks.extend(self._security_scan(files))

        # 5. Required files check
        required = config.get("required_files", [])
        for pattern in required:
            matches = list(output_dir.glob(pattern))
            if not matches:
                report.checks.append(CheckResult(
                    checker=self.name,
                    check_name="required_file",
                    severity=Severity.FAIL,
                    message=f"Required file not found: {pattern}",
                    detail=f"Pattern '{pattern}' matched 0 files in {output_dir}",
                ))
            else:
                for m in matches:
                    report.checks.append(CheckResult(
                        checker=self.name,
                        check_name="required_file",
                        severity=Severity.PASS,
                        message=f"Required file found: {m.relative_to(output_dir)}",
                    ))

        return report

    # ── JSON validation ────────────────────────────────────────────

    def _validate_json(self, filepath: Path) -> list[CheckResult]:
        rel = str(filepath)
        try:
            content = filepath.read_text(encoding="utf-8")
            json.loads(content)
            return [CheckResult(
                checker=self.name, check_name="json_valid",
                severity=Severity.PASS,
                message=f"Valid JSON: {rel}",
            )]
        except json.JSONDecodeError as e:
            return [CheckResult(
                checker=self.name, check_name="json_valid",
                severity=Severity.FAIL,
                message=f"Invalid JSON: {rel}",
                detail=f"Line {e.lineno}, col {e.colno}: {e.msg}",
                file_path=rel,
            )]
        except UnicodeDecodeError:
            return [CheckResult(
                checker=self.name, check_name="json_valid",
                severity=Severity.WARN,
                message=f"Not a UTF-8 text file (skipped): {rel}",
            )]

    # ── YAML validation ────────────────────────────────────────────

    def _validate_yaml(self, filepath: Path) -> list[CheckResult]:
        rel = str(filepath)
        try:
            content = filepath.read_text(encoding="utf-8")
            yaml.safe_load(content)
            return [CheckResult(
                checker=self.name, check_name="yaml_valid",
                severity=Severity.PASS,
                message=f"Valid YAML: {rel}",
            )]
        except yaml.YAMLError as e:
            return [CheckResult(
                checker=self.name, check_name="yaml_valid",
                severity=Severity.FAIL,
                message=f"Invalid YAML: {rel}",
                detail=str(e),
                file_path=rel,
            )]

    # ── Schema compliance ──────────────────────────────────────────

    def _load_schema(self, path: Path) -> dict | None:
        try:
            return json.loads(path.read_text())
        except (json.JSONDecodeError, FileNotFoundError) as e:
            return None

    def _check_schema_compliance(self, filepath: Path, schema: dict) -> CheckResult:
        rel = str(filepath)
        try:
            data = json.loads(filepath.read_text())
            validator = Draft7Validator(schema)
            errors = list(validator.iter_errors(data))
            if not errors:
                return CheckResult(
                    checker=self.name, check_name="schema_compliance",
                    severity=Severity.PASS,
                    message=f"Schema compliant: {rel}",
                )
            # Collect first 3 errors
            details = "; ".join(
                f"{' → '.join(str(p) for p in e.path) or '(root)'}: {e.message}"
                for e in errors[:3]
            )
            return CheckResult(
                checker=self.name, check_name="schema_compliance",
                severity=Severity.FAIL if len(errors) > 0 else Severity.WARN,
                message=f"Schema violations ({len(errors)}): {rel}",
                detail=details,
                file_path=rel,
            )
        except (json.JSONDecodeError, FileNotFoundError) as e:
            return CheckResult(
                checker=self.name, check_name="schema_compliance",
                severity=Severity.WARN,
                message=f"Could not check schema compliance: {rel}",
                detail=str(e),
            )

    # ── Security scan ──────────────────────────────────────────────

    def _security_scan(self, files: list[Path]) -> list[CheckResult]:
        results: list[CheckResult] = []
        # Only scan recognized text files
        text_extensions = {".json", ".yaml", ".yml", ".txt", ".md", ".py", ".js",
                           ".ts", ".go", ".rs", ".sh", ".toml", ".cfg", ".ini",
                           ".xml", ".html", ".css", ".env"}
        text_files = [f for f in files if f.suffix in text_extensions]

        found_any = False
        for fpath in text_files:
            try:
                content = fpath.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            rel = str(fpath)
            for name, pattern, desc in _SECRET_PATTERNS:
                matches = re.finditer(pattern, content, re.IGNORECASE)
                for match in matches:
                    found_any = True
                    # Show line number
                    line_no = content[:match.start()].count('\n') + 1
                    snippet = match.group()[:40] + ("..." if len(match.group()) > 40 else "")
                    results.append(CheckResult(
                        checker=self.name, check_name=f"secret:{name}",
                        severity=Severity.FAIL,
                        message=f"Secret detected ({desc}): {rel}:L{line_no}",
                        detail=f"Matched: {snippet}",
                        file_path=rel,
                    ))

        if not found_any:
            results.append(CheckResult(
                checker=self.name, check_name="security_scan",
                severity=Severity.PASS,
                message="No secrets detected in output files",
            ))

        return results
