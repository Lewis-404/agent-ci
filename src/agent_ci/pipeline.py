"""Verification pipeline orchestrator."""

from pathlib import Path
from typing import Any

from agent_ci.checkers.fact import FactChecker
from agent_ci.checkers.schema import SchemaChecker
from agent_ci.checkers.diff import DiffChecker
from agent_ci.types import PipelineReport


CHECKER_REGISTRY = {
    "schema": SchemaChecker,
    "fact": FactChecker,
    "diff": DiffChecker,
}


async def run_pipeline(output_dir: Path, config: dict[str, Any]) -> PipelineReport:
    """Run all enabled checkers against the output directory."""
    report = PipelineReport()
    pipeline_cfg = config.get("pipeline", {})
    enabled = pipeline_cfg.get("enabled_checkers", ["schema", "fact", "diff"])
    fail_fast = pipeline_cfg.get("fail_fast", False)

    for checker_name in enabled:
        checker_cls = CHECKER_REGISTRY.get(checker_name)
        if checker_cls is None:
            continue

        checker = checker_cls(config=config)
        checker_report = await checker.verify(output_dir)

        if checker_name == "schema":
            report.schema = checker_report
        elif checker_name == "fact":
            report.fact = checker_report
        elif checker_name == "diff":
            report.diff = checker_report

        if fail_fast and checker_report.failed > 0:
            break

    return report
