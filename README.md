# agent-ci-verify

> CI/CD verification pipeline for AI agent outputs.  
> **Don't trust your agent's output — verify it.**

[![CI](https://github.com/Lewis-404/agent-ci-verify/actions/workflows/ci.yml/badge.svg)](https://github.com/Lewis-404/agent-ci-verify/actions/workflows/ci.yml)
[![PyPI version](https://img.shields.io/pypi/v/agent-ci-verify.svg)](https://pypi.org/project/agent-ci-verify/)
[![Python](https://img.shields.io/pypi/pyversions/agent-ci-verify.svg)](https://pypi.org/project/agent-ci-verify/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

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
agent-ci v0.1.0
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
      model: "gpt-4o-mini"

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

```yaml
# .github/workflows/agent-check.yml
- name: Verify agent output
  run: |
    pip install agent-ci-verify
    agent-ci ./output/
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

## License

MIT — see [LICENSE](./LICENSE)
