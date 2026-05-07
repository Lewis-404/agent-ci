"""Diff Checker — compares agent output against baseline to detect regressions."""

from pathlib import Path

from agent_ci.checkers.base import BaseChecker
from agent_ci.types import CheckerReport, CheckResult, Severity


class DiffChecker(BaseChecker):
    """Compares current agent output against a baseline for drift, regression, and anomalies."""

    name = "diff"

    async def verify(self, output_dir: Path) -> CheckerReport:
        report = CheckerReport(checker_name=self.name)
        config = self.config.get("diff", {})
        baseline_dir = config.get("baseline")
        if not baseline_dir:
            report.checks.append(
                CheckResult(
                    checker=self.name,
                    check_name="diff",
                    severity=Severity.WARN,
                    message="No baseline directory configured — skipping diff verification",
                    detail="Set 'diff.baseline' in .agent-ci.yaml to enable diff checks.",
                )
            )
            return report

        baseline = Path(baseline_dir)
        if not baseline.exists():
            report.checks.append(
                CheckResult(
                    checker=self.name,
                    check_name="diff",
                    severity=Severity.FAIL,
                    message=f"Baseline directory not found: {baseline}",
                )
            )
            return report

        text_extensions = {
            ".json",
            ".yaml",
            ".yml",
            ".txt",
            ".md",
            ".py",
            ".js",
            ".ts",
            ".go",
            ".csv",
            ".html",
            ".xml",
            ".toml",
        }
        current_files = {
            file_path.relative_to(output_dir): file_path
            for file_path in output_dir.rglob("*")
            if file_path.is_file() and file_path.suffix in text_extensions
        }
        baseline_files = {
            file_path.relative_to(baseline): file_path
            for file_path in baseline.rglob("*")
            if file_path.is_file() and file_path.suffix in text_extensions
        }

        max_changed = config.get("max_changed_files")
        max_added = config.get("max_added_files")
        max_removed = config.get("max_removed_files")
        semantic_threshold = config.get("semantic_threshold", 0.7)

        added = set(current_files) - set(baseline_files)
        for file_path in sorted(added):
            severity = Severity.FAIL if max_added and len(added) > max_added else Severity.WARN
            report.checks.append(
                CheckResult(
                    checker=self.name,
                    check_name="diff:added",
                    severity=severity,
                    message=f"New file: {file_path}",
                )
            )
        if not added:
            report.checks.append(
                CheckResult(
                    checker=self.name,
                    check_name="diff:added",
                    severity=Severity.PASS,
                    message="No new files detected",
                )
            )

        removed = set(baseline_files) - set(current_files)
        removed_over_limit = max_removed and len(removed) > max_removed
        for file_path in sorted(removed):
            severity = Severity.FAIL if removed_over_limit else Severity.WARN
            report.checks.append(
                CheckResult(
                    checker=self.name,
                    check_name="diff:removed",
                    severity=severity,
                    message=f"Missing file (was in baseline): {file_path}",
                )
            )
        if not removed:
            report.checks.append(
                CheckResult(
                    checker=self.name,
                    check_name="diff:removed",
                    severity=Severity.PASS,
                    message="No files removed since baseline",
                )
            )

        common = set(current_files) & set(baseline_files)
        changed_count = 0
        for file_path in sorted(common):
            current_content = current_files[file_path].read_text(encoding="utf-8")
            baseline_content = baseline_files[file_path].read_text(encoding="utf-8")

            if current_content != baseline_content:
                changed_count += 1
                similarity = self._text_similarity(baseline_content, current_content)

                severity = Severity.PASS
                if similarity < 0.5:
                    severity = Severity.FAIL
                elif similarity < semantic_threshold:
                    severity = Severity.WARN

                report.checks.append(
                    CheckResult(
                        checker=self.name,
                        check_name="diff:changed",
                        severity=severity,
                        message=f"Changed: {file_path} (similarity: {similarity:.1%})",
                        detail=self._generate_diff(
                            baseline_content,
                            current_content,
                            file_path,
                        ),
                        file_path=str(file_path),
                    )
                )

        if changed_count == 0:
            report.checks.append(
                CheckResult(
                    checker=self.name,
                    check_name="diff:changed",
                    severity=Severity.PASS,
                    message="No files changed since baseline",
                )
            )

        if max_changed and changed_count > max_changed:
            report.checks.append(
                CheckResult(
                    checker=self.name,
                    check_name="diff:threshold",
                    severity=Severity.FAIL,
                    message=f"Changed files ({changed_count}) exceed max ({max_changed})",
                )
            )

        return report

    @staticmethod
    def _text_similarity(text_a: str, text_b: str) -> float:
        """Simple token-overlap similarity (Jaccard on word tokens)."""
        if not text_a and not text_b:
            return 1.0
        if not text_a or not text_b:
            return 0.0

        tokens_a = set(text_a.lower().split())
        tokens_b = set(text_b.lower().split())
        intersection = tokens_a & tokens_b
        union = tokens_a | tokens_b
        return len(intersection) / len(union) if union else 0.0

    @staticmethod
    def _generate_diff(
        before: str,
        after: str,
        relpath: Path,
        context_lines: int = 3,
    ) -> str:
        """Generate a unified diff between two strings, capped for report size."""
        import difflib

        diff = list(
            difflib.unified_diff(
                before.splitlines(keepends=True),
                after.splitlines(keepends=True),
                fromfile=f"baseline/{relpath}",
                tofile=f"current/{relpath}",
                n=context_lines,
            )
        )
        if not diff:
            return "(binary or identical)"
        if len(diff) > 50:
            diff = diff[:47] + ["... (truncated)\n"]
        return "".join(diff)
