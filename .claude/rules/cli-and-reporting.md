---
paths:
  - src/agent_ci/cli.py
  - src/agent_ci/report.py
  - tests/test_pipeline.py
---
# CLI and reporting behavior

## CLI and output modes

- `src/agent_ci/cli.py` is the only entry point exposed by `pyproject.toml` (`agent-ci = agent_ci.cli:main`).
- `--json` prints `PipelineReport.to_json()` and exits with `report.exit_code`.
- `--report` writes a self-contained HTML audit report into the verified output directory.
- `--history` reads `.agent-ci-history/*.json` from the current working directory, not from the output directory.
- If both `--json` and `--report` are provided, JSON wins because the CLI exits immediately after emitting JSON.

## HTML report behavior

- `src/agent_ci/report.py` renders a fully self-contained HTML report without external assets.
- Reporting changes should preserve the existing verdict summary contract and avoid introducing network or asset dependencies.

## Pipeline contract reference

- `tests/test_pipeline.py` is the best first file to understand the expected pipeline contract: default checker set, selective checker execution, verdict behavior, and config merge semantics.
