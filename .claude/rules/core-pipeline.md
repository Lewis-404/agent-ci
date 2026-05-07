---
paths:
  - src/agent_ci/config.py
  - src/agent_ci/pipeline.py
  - src/agent_ci/plugins.py
  - src/agent_ci/types.py
---
# Core pipeline architecture

## Config loading

- `src/agent_ci/config.py` defines the canonical defaults for `schema`, `fact`, `diff`, `pipeline`, and `plugins`.
- Config discovery walks up parent directories for `.agent-ci.yaml` when no explicit `--config` is passed.
- Deep merge is additive; `null` values in user config do not overwrite defaults.

## Pipeline orchestration

- `src/agent_ci/pipeline.py` maintains the built-in registry: `schema`, `fact`, `diff`.
- Plugin discovery is merged into that registry at runtime, so plugin names can appear directly in `pipeline.enabled_checkers`.
- `pipeline.parallel=true` and `pipeline.fail_fast=false` runs all checkers concurrently with `asyncio.gather`.
- `fail_fast` only matters in sequential mode; when `fail_fast=true`, the pipeline does not use the parallel branch.
- Checker crashes are converted into synthetic failing `checker_error` results instead of crashing the CLI.
- Built-in checker reports map to dedicated fields on `PipelineReport`; plugin results go to `PipelineReport.extras`.

## Plugin system

- `src/agent_ci/plugins.py` supports two plugin sources:
  - setuptools entry points in group `agent_ci.checkers`
  - directory plugins from `plugins.paths` in config
- Directory plugins are any non-underscored `.py` files that export a `BaseChecker` subclass with a `name` attribute.
- `src/agent_ci/checkers/__init__.py` contains the real `BaseChecker` abstract class; `src/agent_ci/checkers/base.py` is only a re-export shim.

## Report and result model

- `src/agent_ci/types.py` is the contract for `CheckResult`, `CheckerReport`, `PipelineReport`, `Severity`, and `Verdict`.
- Final verdict is derived from the worst severity across all built-in and plugin reports.
- Exit code is `1` only for `REJECT`; warnings still exit `0`.
