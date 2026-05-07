---
paths:
  - src/agent_ci/checkers/**/*
  - tests/test_diff_checker.py
  - tests/test_fact_checker.py
  - tests/test_schema_checker.py
---
# Checker system

## Checker responsibilities

- `src/agent_ci/checkers/schema.py`
  - Validates every JSON and YAML file under the output directory.
  - Optionally validates configured JSON schemas.
  - Scans recognized text-like files for leaked secrets.
  - Enforces `schema.required_files` patterns.
- `src/agent_ci/checkers/fact.py`
  - Re-checks file existence, counts, minimum size, and content assertions.
  - Reconciles live HTTP responses with configured expectations via `httpx`.
  - Supports optional LLM-as-judge checks against matched files.
  - LLM calls try `openai` first, then `litellm`; config and env support is top-level `llm.*` plus `OPENAI_*` / `DEEPSEEK_*` env vars.
- `src/agent_ci/checkers/diff.py`
  - Compares current output against a configured baseline directory.
  - Only text-like extensions participate in diffing.
  - Missing baseline config is a warning, but a configured baseline path that does not exist is a failure.
  - Similarity is token-overlap Jaccard, not embedding-based semantic comparison.

## Test fixtures and expectations

- `tests/fixtures/valid_output/` is the happy-path sample output.
- `tests/fixtures/invalid_output/` intentionally contains invalid content and secret-like material to drive rejection paths.
- `tests/fixtures/baseline/` is used by diff tests to simulate regression comparison.
- Checker changes should be verified with the full pytest suite unless the task is explicitly read-only.
