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


def _severity_style(severity: Severity) -> str:
    return {"pass": "green", "warn": "yellow", "fail": "red"}.get(severity, "white")


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
        table.add_row(
            icon,
            check.check_name,
            check.message,
            check.detail or "",
        )

    console.print(table)
    console.print()


def _print_summary(report: PipelineReport) -> None:
    """Print final verdict summary."""
    verdict = report.verdict

    style_map = {
        Verdict.PASS: "bold green",
        Verdict.PASS_WITH_WARNINGS: "bold yellow",
        Verdict.REJECT: "bold red",
    }
    icon_map = {
        Verdict.PASS: "✅",
        Verdict.PASS_WITH_WARNINGS: "⚠️",
        Verdict.REJECT: "❌",
    }

    # Count totals
    total_checks = 0
    total_pass = 0
    total_warn = 0
    total_fail = 0
    for r in (report.schema, report.fact, report.diff):
        if r:
            total_checks += len(r.checks)
            total_pass += r.passed
            total_warn += r.warnings
            total_fail += r.failed

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

    verdict_text = Text(f"\n  {icon_map[verdict]}  {verdict.value}", style=style_map[verdict])
    summary_text = "\n".join(summary_lines)

    console.print(Panel(
        summary_text + "\n" + str(verdict_text),
        title="[bold]Verdict[/bold]",
        border_style=style_map[verdict].split()[-1],
    ))

    # Exit code
    if verdict == Verdict.REJECT:
        sys.exit(1)


@click.command()
@click.argument("output_dir", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option(
    "-c", "--config", "config_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Path to .agent-ci.yaml config file.",
)
@click.option("--version", is_flag=True, help="Show version and exit.")
def main(output_dir: Path, config_path: Path | None, version: bool) -> None:
    """CI/CD verification pipeline for AI agent outputs.

    OUTPUT_DIR: Directory containing agent output files to verify.
    """
    if version:
        console.print(f"agent-ci v{__version__}")
        return

    # Load config
    try:
        config = load_config(config_path)
    except FileNotFoundError as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Config error:[/red] {e}")
        sys.exit(1)

    console.print(f"\n[bold]agent-ci[/bold] v{__version__}")
    console.print(f"Output dir: [cyan]{output_dir}[/cyan]")
    console.print(f"Checkers: [dim]{', '.join(config['pipeline']['enabled_checkers'])}[/dim]\n")

    # Run pipeline
    report = asyncio.run(run_pipeline(output_dir, config))

    # Print results
    if report.schema:
        _print_checker_report(report.schema, "📋 Schema Checker")
    if report.fact:
        _print_checker_report(report.fact, "🔍 Fact Checker")
    if report.diff:
        _print_checker_report(report.diff, "📊 Diff Checker")

    _print_summary(report)


if __name__ == "__main__":
    main()
