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
@click.argument("output_dir", type=click.Path(exists=True, file_okay=False, path_type=Path), required=False)
@click.option(
    "-c", "--config", "config_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Path to .agent-ci.yaml config file.",
)
@click.option("--json", "output_json", is_flag=True, help="Output machine-readable JSON.")
@click.option("--report", "output_report", is_flag=True, help="Generate self-contained HTML audit report.")
@click.option("--history", is_flag=True, help="Show verification history from .agent-ci-history/.")
@click.option("--version", is_flag=True, help="Show version and exit.")
def main(
    output_dir: Path,
    config_path: Path | None,
    output_json: bool,
    output_report: bool,
    history: bool,
    version: bool,
) -> None:
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

    if history:
        _show_history()
        return

    if output_dir is None:
        console.print("[red]Error:[/red] Missing argument 'OUTPUT_DIR'.")
        console.print("Usage: agent-ci [OPTIONS] OUTPUT_DIR")
        sys.exit(2)

    try:
        config = load_config(config_path)
    except FileNotFoundError as e:
        _fail(f"Config file not found: {e}", output_json)
    except Exception as e:
        _fail(f"Config error: {e}", output_json)

    if not output_json and not output_report:
        console.print(f"\n[bold]agent-ci-verify[/bold] v{__version__}")
        console.print(f"Output dir: [cyan]{output_dir}[/cyan]")
        console.print(f"Checkers: [dim]{', '.join(config['pipeline']['enabled_checkers'])}[/dim]\n")

    report = asyncio.run(run_pipeline(output_dir, config))

    # JSON output (machine)
    if output_json:
        print(report.to_json())
        _save_to_history(report, output_dir)
        sys.exit(report.exit_code)

    # HTML report
    if output_report:
        from agent_ci.report import generate_report
        html = generate_report(report, output_dir, __version__)
        report_path = output_dir / f"agent-ci-report-{_timestamp()}.html"
        report_path.write_text(html, encoding="utf-8")
        _save_to_history(report, output_dir)
        console.print(f"\n[green]✅ Report saved:[/green] {report_path}")
        console.print(f"[dim]{report._all_reports[0].passed if report._all_reports else 0} passed, "
                      f"{sum(r.failed for r in report._all_reports) if report._all_reports else 0} failed[/dim]")
        sys.exit(report.exit_code)

    # Rich terminal output
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


def _timestamp() -> str:
    """Generate a sortable timestamp for filenames."""
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def _history_dir() -> Path:
    """Get or create the history directory."""
    d = Path.cwd() / ".agent-ci-history"
    d.mkdir(exist_ok=True)
    return d


def _save_to_history(report: PipelineReport, output_dir: Path) -> None:
    """Archive verification result to history."""
    try:
        hist = _history_dir()
        record = {
            "timestamp": _timestamp(),
            "output_dir": str(output_dir),
            "report": report.to_dict(),
        }
        import json as _json
        (hist / f"{record['timestamp']}.json").write_text(
            _json.dumps(record, indent=2, ensure_ascii=False)
        )
    except Exception:
        pass  # Non-critical


def _show_history() -> None:
    """Display recent verification history."""
    hist = _history_dir()
    files = sorted(hist.glob("*.json"), reverse=True)
    if not files:
        console.print("[dim]No verification history found.[/dim]")
        return

    console.print(f"\n[bold]📋 Verification History[/bold] [dim]({len(files)} runs)[/dim]\n")

    for f in files[:20]:
        import json as _json
        try:
            data = _json.loads(f.read_text())
            r = data.get("report", {})
            summary = r.get("summary", {})
            verdict = r.get("verdict", "?")
            ts = data.get("timestamp", f.stem)
            od = data.get("output_dir", "?")

            style = {"PASS": "green", "PASS WITH WARNINGS": "yellow", "REJECT": "red"}
            console.print(
                f"  [{style.get(verdict, 'white')}]{verdict:<20}[/{style.get(verdict, 'white')}] "
                f"[dim]{ts}[/dim]  "
                f"{summary.get('passed',0)}✅ {summary.get('warnings',0)}⚠️  {summary.get('failed',0)}❌  "
                f"[dim]→ {od}[/dim]"
            )
        except Exception:
            console.print(f"  [dim]{f.stem} — parse error[/dim]")

    console.print()


if __name__ == "__main__":
    main()
