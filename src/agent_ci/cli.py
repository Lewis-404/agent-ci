"""CLI entry point for agent-ci."""

import asyncio
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from agent_ci import __version__
from agent_ci.config import load_config
from agent_ci.pipeline import run_pipeline
from agent_ci.types import CheckerReport, PipelineReport, Severity, Verdict

console = Console()


def _severity_icon(severity: Severity) -> str:
    return {"pass": "✅", "warn": "⚠️ ", "fail": "❌"}.get(severity, "?")


def _print_checker_report(report: CheckerReport, title: str) -> None:
    """Print a single checker's results as a rich table."""
    if not report or not report.checks:
        return

    table = Table(title=title, show_header=True, header_style="bold")
    table.add_column("Status", width=4)
    table.add_column("Check", style="cyan", width=25)
    table.add_column("Message", style="white")
    table.add_column("Detail", style="dim", width=40)

    for check in report.checks:
        icon = _severity_icon(check.severity)
        table.add_row(icon, check.check_name, check.message, check.detail or "")

    console.print(table)
    console.print()


def _print_summary(report: PipelineReport) -> None:
    """Print final verdict with per-checker and totals."""
    verdict = report.verdict

    style = {"PASS": "bold green", "PASS WITH WARNINGS": "bold yellow", "REJECT": "bold red"}
    icon_map = {"PASS": "✅", "PASS WITH WARNINGS": "⚠️", "REJECT": "❌"}

    # Collect all reports
    builtin = [r for r in (report.schema, report.fact, report.diff) if r]
    extras = list(report.extras.values()) if report.extras else []
    all_reports = builtin + extras

    total_checks = sum(len(r.checks) for r in all_reports)
    total_pass = sum(r.passed for r in all_reports)
    total_warn = sum(r.warnings for r in all_reports)
    total_fail = sum(r.failed for r in all_reports)

    summary_lines = [
        f"  Checks: {total_checks} total | {total_pass} passed | {total_warn} warnings | {total_fail} failed",
    ]
    if report.schema:
        summary_lines.append(
            f"  Schema:  {report.schema.passed}✅ {report.schema.warnings}⚠️  {report.schema.failed}❌"
        )
    if report.fact:
        summary_lines.append(
            f"  Fact:    {report.fact.passed}✅ {report.fact.warnings}⚠️  {report.fact.failed}❌"
        )
    if report.diff:
        summary_lines.append(
            f"  Diff:    {report.diff.passed}✅ {report.diff.warnings}⚠️  {report.diff.failed}❌"
        )
    if extras:
        for name, r in (report.extras or {}).items():
            summary_lines.append(
                f"  {name}:   {r.passed}✅ {r.warnings}⚠️  {r.failed}❌"
            )

    verdict_icon = icon_map.get(verdict.value, "?")
    verdict_style = style.get(verdict.value, "white")

    console.print(Panel(
        "\n".join(summary_lines) + f"\n\n  {verdict_icon}  {verdict.value}",
        title="[bold]Verdict[/bold]",
        border_style=verdict_style.split()[-1],
    ))

    if verdict == Verdict.REJECT:
        sys.exit(1)


@click.command()
@click.argument("output_dir", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option(
    "-c", "--config", "config_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Path to .agent-ci.yaml config file.",
)
@click.option("--json", "output_json", is_flag=True, help="Output machine-readable JSON.")
@click.option("--version", is_flag=True, help="Show version and exit.")
def main(output_dir: Path, config_path: Path | None, output_json: bool, version: bool) -> None:
    """CI/CD verification pipeline for AI agent outputs.

    OUTPUT_DIR: Directory containing agent output files to verify.
    """
    if version:
        if output_json:
            import json as _json
            print(_json.dumps({"name": "agent-ci-verify", "version": __version__}))
        else:
            console.print(f"agent-ci-verify v{__version__}")
        return

    try:
        config = load_config(config_path)
    except FileNotFoundError as e:
        _fail(f"Config file not found: {e}", output_json)
    except Exception as e:
        _fail(f"Config error: {e}", output_json)

    if not output_json:
        console.print(f"\n[bold]agent-ci-verify[/bold] v{__version__}")
        console.print(f"Output dir: [cyan]{output_dir}[/cyan]")
        console.print(f"Checkers: [dim]{', '.join(config['pipeline']['enabled_checkers'])}[/dim]\n")

    report = asyncio.run(run_pipeline(output_dir, config))

    if output_json:
        print(report.to_json())
        sys.exit(report.exit_code)

    if report.schema:
        _print_checker_report(report.schema, "📋 Schema Checker")
    if report.fact:
        _print_checker_report(report.fact, "🔍 Fact Checker")
    if report.diff:
        _print_checker_report(report.diff, "📊 Diff Checker")
    if report.extras:
        for name, r in report.extras.items():
            _print_checker_report(r, f"🔌 {name} (plugin)")

    _print_summary(report)


def _fail(message: str, as_json: bool = False) -> None:
    """Exit with error, optionally as JSON."""
    if as_json:
        import json as _json
        print(_json.dumps({"verdict": "ERROR", "error": message}))
    else:
        console.print(f"[red]Error:[/red] {message}")
    sys.exit(1)


if __name__ == "__main__":
    main()
