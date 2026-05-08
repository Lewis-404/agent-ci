import subprocess
from pathlib import Path


def _pyproject_version_command() -> str:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "release.sh"
    for line in script_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("PYPROJ_VER=$(") and line.endswith(")"):
            return line.removeprefix("PYPROJ_VER=$(").removesuffix(")")
    raise AssertionError("PYPROJ_VER command not found in release.sh")


def test_pyproject_version_extraction_returns_bare_version(tmp_path):
    pyproject_path = tmp_path / "pyproject.toml"
    pyproject_path.write_text(
        '[project]\nname = "agent-ci-verify"\nversion = "1.2.3"\n',
        encoding="utf-8",
    )

    command = _pyproject_version_command()
    result = subprocess.run(
        ["bash", "-lc", command],
        capture_output=True,
        check=True,
        cwd=tmp_path,
        text=True,
    )

    extracted = result.stdout.strip()
    assert extracted == "1.2.3"
    assert "version =" not in extracted
