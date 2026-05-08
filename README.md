# agent-ci-verify

<!-- cspell:ignore deepseek AKIA rglob venv pytest Moltbook -->

> CI/CD verification pipeline for AI agent outputs.  
> **Don't trust your agent's output — verify it.**

[![CI](https://github.com/Lewis-404/agent-ci-verify/actions/workflows/ci.yml/badge.svg)](https://github.com/Lewis-404/agent-ci-verify/actions/workflows/ci.yml)
[![PyPI version](https://img.shields.io/pypi/v/agent-ci-verify.svg)](https://pypi.org/project/agent-ci-verify/)
[![Python](https://img.shields.io/pypi/pyversions/agent-ci-verify.svg)](https://pypi.org/project/agent-ci-verify/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

[中文](./README_CN.md)

---

## Why agent-ci-verify?

AI agents are entering production, but **no one can answer "can I trust this output?"**

Existing tools are all "eval libraries" — you import them and write tests yourself. That's self-review, not independent verification.

**agent-ci-verify is your agent's CI/CD pipeline** — plug it in, and every agent output goes through an independent verification layer before it reaches your users.

## Quick Start

```bash
pip install agent-ci-verify
agent-ci ./agent-output/
```

```
agent-ci-verify v1.1.0
Output dir: ./agent-output/
Checkers: schema, fact, diff

                               📋 Schema Checker
┏━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ ✅   │ json_valid           │                                                ┃
┃ ✅   │ yaml_valid           │                                                ┃
┃ ✅   │ security_scan        │ No secrets detected                            ┃
┗━━━━━━┻━━━━━━━━━━━━━━━━━━━━━━┻━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛

                               🔍 Fact Checker
┏━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ ✅   │ fact:file_count      │ 1 files for '*.json'                           ┃
┃ ✅   │ fact:content_contains│ 'success' found in result.json                 ┃
┗━━━━━━┻━━━━━━━━━━━━━━━━━━━━━━┻━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛

╭────────────────────────────────── Verdict ────────────────────────────────╮
│   ✅  PASS                                                                 │
╰───────────────────────────────────────────────────────────────────────────╯
```

## Three Verification Layers

| Layer | What it checks | Example |
|-------|---------------|---------|
| **Schema** | Format, structure, security | Valid JSON? API key leaked? Required files present? |
| **Fact** | File existence, API reconciliation, LLM judging | Agent claimed `result.json` exists — does it? API returned 200? |
| **Diff** | Regression detection, semantic drift | Output changed vs baseline? Similarity below threshold? |

## Configuration

Drop `.agent-ci.yaml` in your agent project root:

```yaml
pipeline:
  enabled_checkers: [schema, fact, diff]
  fail_fast: false

schema:
  security:
    enabled: true
  required_files:
    - "output/result.json"
  json_schemas:
    schemas/output.schema.json: "output/**/*.json"

fact:
  files:
    - pattern: "output/**/*.json"
      expected_count: 1
      min_size_bytes: 10
      content_checks:
        - type: contains
          value: "success"
        - type: not_contains
          value: "error"
  api:
    - endpoint: "https://api.example.com/health"
      expected_status: 200
  llm_judge:
    - file: "output/answer.md"
      rubric: "Is the answer factually correct?"
      model: "deepseek-v4-flash"

diff:
  baseline: "./baseline-output/"
  semantic_threshold: 0.7
  max_changed_files: 5
```

## Security Scanning

Built-in patterns detect:
- AWS Access Keys (`AKIA...`)
- GitHub Tokens (`ghp_...`)
- OpenAI API Keys (`sk-proj-...`)
- JWT Tokens
- Private Keys (RSA, EC, DSA, OpenSSH)
- Password/Secret assignments

## CI Integration

```bash
# JSON output for programmatic parsing
agent-ci --json ./output/ | jq .verdict
# "PASS"

agent-ci --json ./output/ | jq .summary
# {"total_checks": 6, "passed": 5, "warnings": 1, "failed": 0}
```

```yaml
# .github/workflows/agent-check.yml
- name: Verify agent output
  run: |
    pip install agent-ci-verify
    agent-ci --json ./output/ | tee result.json
```

## Audit Reports & History

```bash
# Generate a self-contained HTML audit report
agent-ci --report ./output/
# ✅ Report saved: ./output/agent-ci-report-20260507-120000.html

# View verification history
agent-ci --history
# 📋 Verification History (42 runs)
#   PASS                 20260507-120000  5✅ 0⚠️  0❌  → ./output/prod/
#   REJECT               20260507-115500  2✅ 1⚠️  2❌  → ./output/staging/
```

Reports are self-contained HTML with dark theme, suitable for auditors and compliance.

## Plugins

Write custom checkers in any `.py` file:

```python
from agent_ci.checkers import BaseChecker
from agent_ci.types import CheckResult, CheckerReport, Severity

class SizeChecker(BaseChecker):
    name = "size"

    async def verify(self, output_dir):
        report = CheckerReport(checker_name=self.name)
        total = sum(f.stat().st_size for f in output_dir.rglob("*") if f.is_file())
        limit = self.config.get("size", {}).get("max_bytes", 10_000_000)
        severity = Severity.FAIL if total > limit else Severity.PASS
        report.checks.append(CheckResult(
            checker=self.name, check_name="size_limit",
            severity=severity,
            message=f"Output size: {total:,} bytes (limit: {limit:,})",
        ))
        return report
```

Configure in `.agent-ci.yaml`:

```yaml
plugins:
  paths:
    - ./checks/

pipeline:
  enabled_checkers: [schema, fact, size]
  parallel: true  # Run all checkers concurrently

size:
  max_bytes: 5000000
```

## Docker

```bash
# Clone and build
git clone https://github.com/Lewis-404/agent-ci-verify.git
cd agent-ci-verify

# Generate API key
export AGENT_CI_API_KEY=$(openssl rand -hex 32)

# Start with docker-compose
docker compose up -d

# Verify it's running
curl http://localhost:8899/health
```

Or build manually:

```bash
docker build -t agent-ci-verify .
docker run -p 8899:8899 \
  -e AGENT_CI_API_KEY="$AGENT_CI_API_KEY" \
  -e AGENT_CI_ALLOWED_ROOTS="/data" \
  -v ./data:/data:ro \
  agent-ci-verify
```

## Development

```bash
git clone https://github.com/Lewis-404/agent-ci-verify.git
cd agent-ci-verify
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest tests/ -v
```

If the shell is not activated, run local verification commands through `./.venv/bin/...`.

## Service Mode (v1.0.5+)

Run as a persistent HTTP API for CI/CD integration. Server mode uses structured logging (structlog), falling back to standard logging if structlog is unavailable.

```bash
# Install with server dependencies
pip install 'agent-ci-verify[server]'

# Start the API server
agent-ci serve

# Health check
curl http://127.0.0.1:8899/health
# {"status":"ok","version":"1.0.5","checkers":{"schema":"healthy","fact":"healthy","diff":"healthy"}}

# Verify agent output via API (API key REQUIRED)
curl -X POST http://127.0.0.1:8899/verify \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key" \
  -d '{"output_directory": "/path/to/agent/output"}'
```

> **Note:** API key authentication is REQUIRED for `POST /verify`. Generate a key with `openssl rand -hex 32` and set the `AGENT_CI_API_KEY` environment variable before starting the server.

Customize host/port: `agent-ci serve --host 0.0.0.0 --port 8080`.

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| AGENT_CI_API_KEY | *(required)* | API key for POST /verify authentication |
| AGENT_CI_RATE_LIMIT | 10 | Max requests per window per IP+key |
| AGENT_CI_RATE_WINDOW | 60 | Rate limit window in seconds |

## Design Rationale

This project started from a deep-dive report: after scanning 25+ Moltbook posts, 40+ HN discussions, and 10+ GitHub repositories, the conclusion was the same: **everyone is building eval libraries, but almost no one is building verification infrastructure.**

- Most competing tools follow the library pattern: `import tool → write tests → run tests`
- Enterprises hesitate to put agents into production not because agents are always weak, but because they cannot answer whether the output is trustworthy
- The more agents teams deploy, the more verification demand grows — this is an infrastructure opportunity

See the [deep-dive report](https://github.com/Lewis-404/bot-shared-knowledge/blob/main/best-practices/2026-05-06-agent-verification-deep-dive.md) for more context.

## License

MIT — see [LICENSE](./LICENSE)
