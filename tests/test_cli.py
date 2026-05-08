"""Tests for agent-ci CLI entry point."""

import json

import pytest
import yaml
from click.testing import CliRunner

from agent_ci.cli import main


# ──────────────────────────────────────────────
#  Existing test (preserved)
# ──────────────────────────────────────────────
def test_cli_accepts_output_directory_argument(valid_output):
    runner = CliRunner()

    result = runner.invoke(main, [str(valid_output)])

    assert result.exit_code == 0, result.output
    assert "Verdict" in result.output


# ──────────────────────────────────────────────
#  --help
# ──────────────────────────────────────────────
def test_help():
    """--help prints usage and exits 0."""
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "Usage:" in result.output or "usage:" in result.output.lower()
    assert "OUTPUT_DIR" in result.output
    assert "--json" in result.output
    assert "--report" in result.output
    assert "--history" in result.output
    assert "--serve" in result.output


# ──────────────────────────────────────────────
#  --version
# ──────────────────────────────────────────────
def test_version():
    """--version prints version string."""
    runner = CliRunner()
    result = runner.invoke(main, ["--version"])
    assert result.exit_code == 0
    assert "agent-ci-verify" in result.output


def test_version_json():
    """--version --json prints JSON with name + version."""
    runner = CliRunner()
    result = runner.invoke(main, ["--version", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output.strip())
    assert data["name"] == "agent-ci-verify"
    assert "version" in data


def test_version_json_output_dir_ignored(valid_output):
    """--version takes precedence — output_dir is ignored."""
    runner = CliRunner()
    result = runner.invoke(main, ["--version", str(valid_output)])
    assert result.exit_code == 0
    assert "agent-ci-verify" in result.output


# ──────────────────────────────────────────────
#  Missing / invalid output_dir
# ──────────────────────────────────────────────
def test_missing_output_dir():
    """No output_dir and no flags → usage error, exit 2."""
    runner = CliRunner()
    result = runner.invoke(main, [])
    assert result.exit_code == 2
    assert "Missing argument" in result.output or "Error" in result.output


def test_invalid_path_nonexistent(tmp_path):
    """Non-existent directory rejected by Click path validation."""
    bad_path = tmp_path / "does_not_exist"
    runner = CliRunner()
    result = runner.invoke(main, [str(bad_path)])
    assert result.exit_code != 0
    assert (
        "Error" in result.output
        or "Invalid" in result.output
        or "does not exist" in result.output.lower()
    )


def test_invalid_path_is_file(tmp_path):
    """File (not directory) rejected by Click path validation."""
    some_file = tmp_path / "hello.txt"
    some_file.write_text("i am a file")
    runner = CliRunner()
    result = runner.invoke(main, [str(some_file)])
    assert result.exit_code != 0
    # Click will complain that it's not a directory
    assert "Error" in result.output or "directory" in result.output.lower()


# ──────────────────────────────────────────────
#  --config with missing / bad config
# ──────────────────────────────────────────────
def test_config_file_not_found(valid_output, monkeypatch):
    """Mock load_config FileNotFoundError → _fail (rich error), exit 1."""
    from agent_ci import cli as cli_mod

    def _raise(*args, **kwargs):
        raise FileNotFoundError("Config file not found: /bad/path.yaml")

    monkeypatch.setattr(cli_mod, "load_config", _raise)
    runner = CliRunner()
    result = runner.invoke(main, [str(valid_output)])
    assert result.exit_code == 1
    assert "Error" in result.output
    assert "Config file not found" in result.output


def test_config_file_not_found_json(valid_output, monkeypatch):
    """Mock load_config FileNotFoundError + --json → JSON error output."""
    from agent_ci import cli as cli_mod

    def _raise(*args, **kwargs):
        raise FileNotFoundError("Config file not found: /bad/path.yaml")

    monkeypatch.setattr(cli_mod, "load_config", _raise)
    runner = CliRunner()
    result = runner.invoke(main, ["--json", str(valid_output)])
    assert result.exit_code == 1
    data = json.loads(result.output.strip())
    assert data["verdict"] == "ERROR"
    assert "Config file not found" in data["error"]


def test_config_general_error(valid_output, monkeypatch):
    """Mock load_config to raise a generic Exception → _fail."""
    from agent_ci import cli as cli_mod

    def _raise(*args, **kwargs):
        raise ValueError("Something went wrong parsing config")

    monkeypatch.setattr(cli_mod, "load_config", _raise)
    runner = CliRunner()
    result = runner.invoke(main, [str(valid_output)])
    assert result.exit_code == 1
    assert "Error" in result.output
    assert "Config error" in result.output


def test_config_general_error_json(valid_output, monkeypatch):
    """Mock load_config generic exception + --json → JSON error."""
    from agent_ci import cli as cli_mod

    def _raise(*args, **kwargs):
        raise RuntimeError("bad yaml")

    monkeypatch.setattr(cli_mod, "load_config", _raise)
    runner = CliRunner()
    result = runner.invoke(main, ["--json", str(valid_output)])
    assert result.exit_code == 1
    data = json.loads(result.output.strip())
    assert data["verdict"] == "ERROR"


# ──────────────────────────────────────────────
#  --json output
# ──────────────────────────────────────────────
def test_json_output(valid_output):
    """--json runs the pipeline and prints JSON report, exit 0."""
    runner = CliRunner()
    result = runner.invoke(main, ["--json", str(valid_output)])
    # Default config has no baseline → diff produces WARN → PASS WITH WARNINGS → exit 0
    assert result.exit_code == 0
    data = json.loads(result.output.strip())
    assert "verdict" in data
    assert "summary" in data
    assert "schema" in data
    assert isinstance(data["summary"]["passed"], int)


def test_json_output_reject(valid_output, tmp_path):
    """--json with a config that forces a FAIL → REJECT → exit 1."""
    # Write a config that requires a file that doesn't exist
    config = {"schema": {"required_files": ["ghost-file.nope"]}}
    config_path = tmp_path / "reject-config.yaml"
    config_path.write_text(yaml.dump(config))

    runner = CliRunner()
    result = runner.invoke(
        main,
        ["--json", "--config", str(config_path), str(valid_output)],
    )
    assert result.exit_code == 1
    data = json.loads(result.output.strip())
    assert data["verdict"] == "REJECT"
    assert data["exit_code"] == 1


# ──────────────────────────────────────────────
#  --report output
# ──────────────────────────────────────────────
def test_report_output(valid_output):
    """--report generates an HTML file and reports success."""
    runner = CliRunner()
    result = runner.invoke(main, ["--report", str(valid_output)])
    # Default: PASS WITH WARNINGS → exit 0
    assert result.exit_code == 0
    assert "Report saved" in result.output
    # Find the generated report file
    reports = list(valid_output.glob("agent-ci-report-*.html"))
    assert len(reports) > 0, f"No report found in {valid_output}"


def test_report_output_reject(valid_output, tmp_path):
    """--report with force-fail config → REJECT → exit 1, report still saved."""
    config = {"schema": {"required_files": ["never-there.file"]}}
    config_path = tmp_path / "fail-config.yaml"
    config_path.write_text(yaml.dump(config))

    runner = CliRunner()
    result = runner.invoke(
        main,
        ["--report", "--config", str(config_path), str(valid_output)],
    )
    assert result.exit_code == 1
    assert "Report saved" in result.output
    reports = list(valid_output.glob("agent-ci-report-*.html"))
    assert len(reports) > 0


# ──────────────────────────────────────────────
#  --history
# ──────────────────────────────────────────────
def test_history_empty(tmp_path, monkeypatch):
    """--history with no history files shows empty message."""
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    result = runner.invoke(main, ["--history"])
    assert result.exit_code == 0
    assert "No verification history found" in result.output


def test_history_with_entries(tmp_path, monkeypatch):
    """--history with history files displays them."""
    history_dir = tmp_path / ".agent-ci-history"
    history_dir.mkdir()

    # Write two valid history records
    records = [
        {
            "timestamp": "20250101-120000",
            "output_dir": "/tmp/run1",
            "report": {
                "verdict": "PASS",
                "summary": {"passed": 3, "warnings": 0, "failed": 0},
            },
        },
        {
            "timestamp": "20250101-130000",
            "output_dir": "/tmp/run2",
            "report": {
                "verdict": "PASS WITH WARNINGS",
                "summary": {"passed": 2, "warnings": 1, "failed": 0},
            },
        },
    ]
    for rec in records:
        (history_dir / f"{rec['timestamp']}.json").write_text(
            json.dumps(rec, ensure_ascii=False)
        )

    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    result = runner.invoke(main, ["--history"])
    assert result.exit_code == 0
    assert "Verification History" in result.output
    assert "PASS" in result.output
    assert "PASS WITH WARNINGS" in result.output
    assert "2 runs" in result.output


def test_history_parse_error(tmp_path, monkeypatch):
    """--history with a corrupt JSON file shows parse error gracefully."""
    history_dir = tmp_path / ".agent-ci-history"
    history_dir.mkdir()

    # Write one corrupt file
    (history_dir / "20250101-120000.json").write_text("not valid json {{{")

    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    result = runner.invoke(main, ["--history"])
    assert result.exit_code == 0
    assert "Verification History" in result.output
    assert "parse error" in result.output


def test_history_shows_max_20(tmp_path, monkeypatch):
    """--history caps display at 20 entries but shows total count."""
    history_dir = tmp_path / ".agent-ci-history"
    history_dir.mkdir()

    for i in range(25):
        rec = {
            "timestamp": f"20250101-{i:06d}",
            "output_dir": f"/tmp/run{i}",
            "report": {
                "verdict": "PASS",
                "summary": {"passed": 1, "warnings": 0, "failed": 0},
            },
        }
        (history_dir / f"{rec['timestamp']}.json").write_text(json.dumps(rec))

    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    result = runner.invoke(main, ["--history"])
    assert result.exit_code == 0
    assert "25 runs" in result.output


# ──────────────────────────────────────────────
#  --serve
# ──────────────────────────────────────────────
def test_serve_flag(monkeypatch):
    """--serve reaches the serve code path (mock _start_server to avoid blocking)."""
    from agent_ci import cli as cli_mod

    called = {}

    def _fake_start(config_path, host, port):
        called["args"] = (config_path, host, port)

    monkeypatch.setattr(cli_mod, "_start_server", _fake_start)

    runner = CliRunner()
    result = runner.invoke(main, ["--serve", "--host", "0.0.0.0", "--port", "9876"])
    assert result.exit_code == 0
    assert called["args"] == (None, "0.0.0.0", 9876)


def test_serve_import_error(monkeypatch):
    """_start_server with FastAPI not installed → ImportError → SystemExit(1)."""
    import builtins

    from agent_ci.cli import _start_server

    original_import = builtins.__import__

    def _mock_import(name, *args, **kwargs):
        if name == "agent_ci.server":
            raise ImportError("No module named 'fastapi'")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _mock_import)

    with pytest.raises(SystemExit) as exc_info:
        _start_server(None, "127.0.0.1", 8899)
    assert exc_info.value.code == 1


# ──────────────────────────────────────────────
#  Edge cases
# ──────────────────────────────────────────────
def test_json_and_report_mutually_exclusive_style(valid_output):
    """Both --json and --report: --json takes precedence (first if wins)."""
    runner = CliRunner()
    result = runner.invoke(main, ["--json", "--report", str(valid_output)])
    assert result.exit_code == 0
    # JSON path hits first, so we get JSON on stdout (not HTML report message)
    data = json.loads(result.output.strip())
    assert "verdict" in data


def test_default_with_config_flag(valid_output, tmp_path):
    """Pass --config with a valid YAML file; should run successfully."""
    config = {"pipeline": {"enabled_checkers": ["schema"]}}
    config_path = tmp_path / "custom.yaml"
    config_path.write_text(yaml.dump(config))

    runner = CliRunner()
    result = runner.invoke(main, ["--config", str(config_path), str(valid_output)])
    assert result.exit_code == 0
    assert "Verdict" in result.output


def test_default_banner_printed(valid_output):
    """Default mode (no --json/--report) prints banner with version + dir info."""
    runner = CliRunner()
    result = runner.invoke(main, [str(valid_output)])
    assert "agent-ci-verify" in result.output
    assert "Output dir:" in result.output
    assert "Checkers:" in result.output


# ──────────────────────────────────────────────
#  Additional: _save_to_history error resilience
# ──────────────────────────────────────────────
def test_json_save_history_swallows_errors(valid_output, monkeypatch):
    """If history dir creation fails, --json still exits 0 and prints JSON."""
    from agent_ci import cli as cli_mod

    # Mock _history_dir inside _save_to_history to raise — caught by except Exception
    def _boom():
        raise OSError("disk full")

    monkeypatch.setattr(cli_mod, "_history_dir", _boom)

    runner = CliRunner()
    result = runner.invoke(main, ["--json", str(valid_output)])
    assert result.exit_code == 0
    data = json.loads(result.output.strip())
    assert "verdict" in data
