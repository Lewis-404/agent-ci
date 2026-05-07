# Development commands

Use the project virtual environment when available. In this repo, the checked-in workflow is usually:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

If the shell is not activated, call tools through `./.venv/bin/...`.

## Test and quality checks

```bash
./.venv/bin/pytest tests/ -v
./.venv/bin/pytest tests/test_pipeline.py -v
./.venv/bin/pytest tests/test_pipeline.py::test_pipeline_verdict_reject -v
./.venv/bin/ruff check src/ tests/
./.venv/bin/mypy src/ --ignore-missing-imports
```

## Run the CLI locally

```bash
./.venv/bin/agent-ci tests/fixtures/valid_output
./.venv/bin/agent-ci tests/fixtures/invalid_output
./.venv/bin/agent-ci --json tests/fixtures/valid_output
./.venv/bin/agent-ci --report tests/fixtures/valid_output
./.venv/bin/agent-ci --history
./.venv/bin/agent-ci --version
```

## Packaging / install smoke checks

```bash
pip install -e .
./.venv/bin/agent-ci tests/fixtures/valid_output
```

## CI expectations

The GitHub Actions workflow in `.github/workflows/ci.yml` is the source of truth for repository checks:

```bash
pip install -e ".[dev]"
ruff check src/ tests/
mypy src/ --ignore-missing-imports
pytest tests/ -v --tb=short --cov=agent_ci --cov-report=term
```

CI also runs smoke checks by installing the package and executing the CLI against the fixture directories.
