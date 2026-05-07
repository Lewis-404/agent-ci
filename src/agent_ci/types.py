"""Shared types and dataclasses for agent-ci."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


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
    detail: Optional[str] = None
    file_path: Optional[str] = None


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


@dataclass
class PipelineReport:
    """Complete verification pipeline report."""

    fact: Optional[CheckerReport] = None
    schema: Optional[CheckerReport] = None
    diff: Optional[CheckerReport] = None

    @property
    def verdict(self) -> Verdict:
        worst = Severity.PASS
        for report in (self.fact, self.schema, self.diff):
            if report and report.worst_severity == Severity.FAIL:
                return Verdict.REJECT
            if report and report.worst_severity == Severity.WARN:
                worst = Severity.WARN
        if worst == Severity.WARN:
            return Verdict.PASS_WITH_WARNINGS
        return Verdict.PASS
