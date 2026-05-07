from click.testing import CliRunner

from agent_ci.cli import main


def test_cli_accepts_output_directory_argument(valid_output):
    runner = CliRunner()

    result = runner.invoke(main, [str(valid_output)])

    assert result.exit_code == 0, result.output
    assert "Verdict" in result.output
