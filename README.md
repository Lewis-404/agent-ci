# agent-ci

> CI/CD verification pipeline for AI agent outputs.

**Status: Alpha** — core checkers working, CLI functional, tests in progress.

## Quick Start

```bash
pip install agent-ci
agent-ci run ./agent-output/
```

## Checkers

- **Schema** — JSON/YAML validation, security scanning, required files
- **Fact** — file existence, API reconciliation, LLM-as-Judge
- **Diff** — baseline comparison, semantic similarity, regression detection

## Configuration

Drop a `.agent-ci.yaml` in your project root:

```yaml
pipeline:
  enabled_checkers: [schema, fact, diff]

schema:
  security: { enabled: true }
  required_files: ["output/result.json"]

fact:
  files:
    - pattern: "output/**/*.json"
      expected_count: 1
```

## License

MIT — see [LICENSE](./LICENSE)
