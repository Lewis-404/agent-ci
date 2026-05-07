"""CLI entry point for agent-ci."""

import asyncio
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

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
    table.add_column("Check", style="cyan", width=20)
    table.add_column("Message", width=40)
    table.add_column("Detail", style="dim", width=40)

    for check in report.checks:
        table.add_row(
            _severity_icon(check.severity),
            check.check_name,
            check.message,
            check.detail or "",
        )

    console.print(table)
    console.print()


def _print_summary(report: PipelineReport) -> None:
    """Print final verdict with per-checker and totals."""
    verdict = report.verdict
    style = {
        "PASS": "bold green",
        "PASS WITH WARNINGS": "bold yellow",
        "REJECT": "bold red",
    }
    icon_map = {
        "PASS": "✅",
        "PASS WITH WARNINGS": "⚠️",
        "REJECT": "❌",
    }

    builtin_reports = [
        checker_report
        for checker_report in (report.schema, report.fact, report.diff)
        if checker_report
    ]
    extra_reports = list(report.extras.values()) if report.extras else []
    all_reports = builtin_reports + extra_reports

    total_checks = sum(len(checker_report.checks) for checker_report in all_reports)
    total_pass = sum(checker_report.passed for checker_report in all_reports)
    total_warn = sum(checker_report.warnings for checker_report in all_reports)
    total_fail = sum(checker_report.failed for checker_report in all_reports)

    summary_lines = [
        (
            f"  Checks: {total_checks} total | {total_pass} passed | "
            f"{total_warn} warnings | {total_fail} failed"
        ),
    ]
    if report.schema:
        summary_lines.append(
            f"  Schema:  {report.schema.passed}✅ "
            f"{report.schema.warnings}⚠️  {report.schema.failed}❌"
        )
    if report.fact:
        summary_lines.append(
            f"  Fact:    {report.fact.passed}✅ "
            f"{report.fact.warnings}⚠️  {report.fact.failed}❌"
        )
    if report.diff:
        summary_lines.append(
            f"  Diff:    {report.diff.passed}✅ "
            f"{report.diff.warnings}⚠️  {report.diff.failed}❌"
        )
    if extra_reports:
        for name, checker_report in (report.extras or {}).items():
            summary_lines.append(
                f"  {name}:   {checker_report.passed}✅ "
                f"{checker_report.warnings}⚠️  {checker_report.failed}❌"
            )

    verdict_icon = icon_map.get(verdict.value, "?")
    verdict_style = style.get(verdict.value, "white")
    console.print(
        Panel(
            "\n".join(summary_lines) + f"\n\n  {verdict_icon}  {verdict.value}",
            title="[bold]Verdict[/bold]",
            border_style=verdict_style.split()[-1],
        )
    )

    if verdict == Verdict.REJECT:
        sys.exit(1)


@click.command()
@click.argument(
    "output_dir",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    required=False,
)
@click.option(
    "-c",
    "--config",
    "config_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Path to .agent-ci.yaml config file.",
)
@click.option(
    "--json",
    "output_json",
    is_flag=True,
    help="Output machine-readable JSON.",
)
@click.option(
    "--report",
    "output_report",
    is_flag=True,
    help="Generate self-contained HTML audit report.",
)
@click.option(
    "--history",
    is_flag=True,
    help="Show verification history from .agent-ci-history/.",
)
@click.option("--version", is_flag=True, help="Show version and exit.")
@click.option(
    "--serve",
    is_flag=True,
    help="Start the verification API server.",
)
@click.option(
    "--host",
    default="127.0.0.1",
    help="Host to bind the server to (with --serve).",
    show_default=True,
)
@click.option(
    "--port",
    default=8899,
    help="Port to listen on (with --serve).",
    show_default=True,
)
def main(
    output_dir: Path | None,
    config_path: Path | None,
    output_json: bool,
    output_report: bool,
    history: bool,
    version: bool,
    serve: bool,
    host: str,
    port: int,
) -> None:
    """CI/CD verification pipeline for AI agent outputs.

    Default mode: agent-ci [OPTIONS] OUTPUT_DIR
    Server mode: agent-ci --serve [OPTIONS]

    """
    if version:
        if output_json:
            import json as _json

            print(_json.dumps({"name": "agent-ci-verify", "version": __version__}))
        else:
            console.print(f"agent-ci-verify v{__version__}")
        return

    if serve:
        _start_server(config_path, host, port)
        return

    if history:
        _show_history()
        return

    if output_dir is None:
        console.print("[red]Error:[/red] Missing argument 'OUTPUT_DIR'.")
        console.print("Usage: agent-ci [OPTIONS] OUTPUT_DIR")
        console.print("       agent-ci --serve [OPTIONS]")
        sys.exit(2)

    try:
        config = load_config(config_path)
    except FileNotFoundError as error:
        _fail(f"Config file not found: {error}", output_json)
    except Exception as error:
        _fail(f"Config error: {error}", output_json)

    if not output_json and not output_report:
        console.print(f"\n[bold]agent-ci-verify[/bold] v{__version__}")
        console.print(f"Output dir: [cyan]{output_dir}[/cyan]")
        console.print(
            "Checkers: "
            f"[dim]{', '.join(config['pipeline']['enabled_checkers'])}[/dim]\n"
        )

    report = asyncio.run(run_pipeline(output_dir, config))

    if output_json:
        print(report.to_json())
        _save_to_history(report, output_dir)
        sys.exit(report.exit_code)

    if output_report:
        from agent_ci.report import generate_report

        html = generate_report(report, output_dir, __version__)
        report_path = output_dir / f"agent-ci-report-{_timestamp()}.html"
        report_path.write_text(html, encoding="utf-8")
        _save_to_history(report, output_dir)

        total_passed = sum(
            checker_report.passed for checker_report in report._all_reports
        )
        total_failed = sum(
            checker_report.failed for checker_report in report._all_reports
        )
        console.print(f"\n[green]✅ Report saved:[/green] {report_path}")
        console.print(f"[dim]{total_passed} passed, {total_failed} failed[/dim]")
        sys.exit(report.exit_code)

    if report.schema:
        _print_checker_report(report.schema, "📋 Schema Checker")
    if report.fact:
        _print_checker_report(report.fact, "🔍 Fact Checker")
    if report.diff:
        _print_checker_report(report.diff, "📊 Diff Checker")
    if report.extras:
        for name, checker_report in report.extras.items():
            _print_checker_report(checker_report, f"🔌 {name} (plugin)")

    _print_summary(report)


def _start_server(config_path: Path | None, host: str, port: int) -> None:
    """Start the verification API server."""
    try:
        from agent_ci.server import create_app
    except ImportError as import_error:
        console.print(
            "[red]Error:[/red] Server dependencies not installed. "
            "Run: pip install 'agent-ci-verify[server]'"
        )
        raise SystemExit(1) from import_error

    application = create_app(config_path=str(config_path) if config_path else None)
    console.print(f"\n[bold]agent-ci-verify[/bold] API Server v{__version__}")
    console.print(f"Listening on [cyan]http://{host}:{port}[/cyan]")
    console.print("  [dim]POST /verify[/dim]  — verify agent output directory")
    console.print("  [dim]GET /health[/dim]   — health check")
    console.print()

    import uvicorn

    uvicorn.run(application, host=host, port=port, log_level="warning")


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
    history_dir = Path.cwd() / ".agent-ci-history"
    history_dir.mkdir(exist_ok=True)
    return history_dir


def _save_to_history(report: PipelineReport, output_dir: Path) -> None:
    """Archive verification result to history."""
    try:
        history_dir = _history_dir()
        record = {
            "timestamp": _timestamp(),
            "output_dir": str(output_dir),
            "report": report.to_dict(),
        }

        import json as _json

        (history_dir / f"{record['timestamp']}.json").write_text(
            _json.dumps(record, indent=2, ensure_ascii=False)
        )
    except Exception:
        pass


def _show_history() -> None:
    """Display recent verification history."""
    history_dir = _history_dir()
    files = sorted(history_dir.glob("*.json"), reverse=True)
    if not files:
        console.print("[dim]No verification history found.[/dim]")
        return

    console.print(
        f"\n[bold]📋 Verification History[/bold] [dim]({len(files)} runs)[/dim]\n"
    )

    for file_path in files[:20]:
        import json as _json

        try:
            data = _json.loads(file_path.read_text())
            report = data.get("report", {})
            summary = report.get("summary", {})
            verdict = report.get("verdict", "?")
            timestamp = data.get("timestamp", file_path.stem)
            output_dir = data.get("output_dir", "?")
            style = {
                "PASS": "green",
                "PASS WITH WARNINGS": "yellow",
                "REJECT": "red",
            }

            console.print(
                f"  [{style.get(verdict, 'white')}]"
                f"{verdict:<20}"
                f"[/{style.get(verdict, 'white')}] "
                f"[dim]{timestamp}[/dim]  "
                f"{summary.get('passed', 0)}✅ "
                f"{summary.get('warnings', 0)}⚠️  "
                f"{summary.get('failed', 0)}❌  "
                f"[dim]→ {output_dir}[/dim]"
            )
        except Exception:
            console.print(f"  [dim]{file_path.stem} — parse error[/dim]")

    console.print()


if __name__ == "__main__":
    main()
