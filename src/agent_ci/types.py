"""Shared types and dataclasses for agent-ci."""

import json
from dataclasses import asdict, dataclass, field
from enum import Enum


class Severity(str, Enum):
    """Check result severity."""

    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"


class Verdict(str, Enum):
    """Final pipeline verdict."""

    PASS = "PASS"
    PASS_WITH_WARNINGS = "PASS WITH WARNINGS"
    REJECT = "REJECT"


@dataclass
class CheckResult:
    """Single check result."""

    checker: str
    check_name: str
    severity: Severity
    message: str
    detail: str | None = None
    file_path: str | None = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["severity"] = self.severity.value
        return {k: v for k, v in d.items() if v is not None}


@dataclass
class CheckerReport:
    """Aggregated results from one checker."""

    checker_name: str
    checks: list[CheckResult] = field(default_factory=list)

    @property
    def passed(self) -> int:
        return sum(1 for c in self.checks if c.severity == Severity.PASS)

    @property
    def warnings(self) -> int:
        return sum(1 for c in self.checks if c.severity == Severity.WARN)

    @property
    def failed(self) -> int:
        return sum(1 for c in self.checks if c.severity == Severity.FAIL)

    @property
    def worst_severity(self) -> Severity:
        if self.failed > 0:
            return Severity.FAIL
        if self.warnings > 0:
            return Severity.WARN
        return Severity.PASS

    def to_dict(self) -> dict:
        return {
            "checker": self.checker_name,
            "summary": {
                "passed": self.passed,
                "warnings": self.warnings,
                "failed": self.failed,
                "total": len(self.checks),
            },
            "checks": [c.to_dict() for c in self.checks],
        }


@dataclass
class PipelineReport:
    """Complete verification pipeline report."""

    fact: CheckerReport | None = None
    schema: CheckerReport | None = None
    diff: CheckerReport | None = None
    extras: dict[str, CheckerReport] | None = None

    @property
    def _all_reports(self) -> list[CheckerReport]:
        reports = [r for r in (self.schema, self.fact, self.diff) if r]
        if self.extras:
            reports.extend(self.extras.values())
        return reports

    @property
    def verdict(self) -> Verdict:
        worst = Severity.PASS
        for report in self._all_reports:
            if report.worst_severity == Severity.FAIL:
                return Verdict.REJECT
            if report.worst_severity == Severity.WARN:
                worst = Severity.WARN
        if worst == Severity.WARN:
            return Verdict.PASS_WITH_WARNINGS
        return Verdict.PASS

    @property
    def exit_code(self) -> int:
        return 1 if self.verdict == Verdict.REJECT else 0

    def to_dict(self) -> dict:
        result: dict = {
            "verdict": self.verdict.value,
            "exit_code": self.exit_code,
        }
        if self.schema:
            result["schema"] = self.schema.to_dict()
        if self.fact:
            result["fact"] = self.fact.to_dict()
        if self.diff:
            result["diff"] = self.diff.to_dict()
        if self.extras:
            result["extras"] = {k: v.to_dict() for k, v in self.extras.items()}
        # Global summary
        reports = self._all_reports
        result["summary"] = {
            "total_checks": sum(len(r.checks) for r in reports),
            "passed": sum(r.passed for r in reports),
            "warnings": sum(r.warnings for r in reports),
            "failed": sum(r.failed for r in reports),
        }
        return result

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)
