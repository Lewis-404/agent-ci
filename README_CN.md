# agent-ci-verify

> AI Agent 产出的 CI/CD 验证管道。  
> **别信你的 Agent —— 验证它。**

[![CI](https://github.com/Lewis-404/agent-ci-verify/actions/workflows/ci.yml/badge.svg)](https://github.com/Lewis-404/agent-ci-verify/actions/workflows/ci.yml)
[![PyPI version](https://img.shields.io/pypi/v/agent-ci-verify.svg)](https://pypi.org/project/agent-ci-verify/)
[![Python](https://img.shields.io/pypi/pyversions/agent-ci-verify.svg)](https://pypi.org/project/agent-ci-verify/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

[English](./README.md)

---

## 为什么需要它？

AI Agent 正在进入生产环境，但**没人能回答"这个产出我能信吗"**。

市面上的工具全是"评估库"——import 进来自己写测试，本质上是自审自查，不是独立验证。

**agent-ci-verify 是 Agent 世界的 CI/CD 管道**——Agent 跑完任务，产出自动进入验证层，过审才放行。

## 快速开始

```bash
pip install agent-ci-verify
agent-ci ./agent-output/
```

```
agent-ci-verify v0.2.0
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

## 三层验证

| 层级 | 做什么 | 举例 |
|------|--------|------|
| **Schema（格式）** | 格式校验、结构合规、安全扫描 | JSON 合法吗？泄露了 API Key？必选文件在吗？ |
| **Fact（事实）** | 文件存在性、API 对账、LLM 裁判 | Agent 说生成了 result.json——真的吗？API 返回了 200？ |
| **Diff（对比）** | 回归检测、语义漂移 | 产出比基线变了多少？相似度跌破阈值了吗？ |

## 配置

在 Agent 项目根目录放一个 `.agent-ci.yaml`：

```yaml
pipeline:
  enabled_checkers: [schema, fact, diff]
  fail_fast: false

schema:
  security:
    enabled: true                # 扫描密钥泄露
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
  llm_judge:                     # 独立 LLM 裁判
    - file: "output/answer.md"
      rubric: "检查回答是否事实正确且完整"
      model: "deepseek-v4-flash"

diff:
  baseline: "./baseline-output/"
  semantic_threshold: 0.7
  max_changed_files: 5
```

## 安全扫描

内置检测模式：

- AWS Access Key (`AKIA...`)
- GitHub Token (`ghp_...`)
- OpenAI API Key (`sk-proj-...`)
- JWT Token
- 私钥 (RSA、EC、DSA、OpenSSH)
- 密码/密钥赋值语句

## CI 集成

```bash
# JSON 输出，方便程序解析
agent-ci --json ./output/ | jq .verdict
# "PASS"

agent-ci --json ./output/ | jq .summary
# {"total_checks": 6, "passed": 5, "warnings": 1, "failed": 0}
```

```yaml
# .github/workflows/agent-check.yml
- name: 验证 Agent 产出
  run: |
    pip install agent-ci-verify
    agent-ci --json ./output/ | tee result.json
```

## 开发

```bash
git clone https://github.com/Lewis-404/agent-ci-verify.git
cd agent-ci-verify
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest tests/ -v
```

## 设计思路

这个项目的起源是一份深挖报告——我们扫描了 Moltbook 25+ 帖子、HN 40+ 讨论、GitHub 10+ 仓库后发现：**所有人都在做"评估库"（Library），没有人在做"验证基础设施"（Infrastructure）。**

- 竞品全是 `import giskard → 写测试 → 跑测试` 的库模式
- 企业不敢把 Agent 放生产，不是因为 Agent 笨，是因为没法回答"产出能信吗"
- Agent 越多，验证需求越大——这是一个**卖铲子给淘金者**的机会

详见[深挖报告](https://github.com/Lewis-404/bot-shared-knowledge/blob/main/best-practices/2026-05-06-agent-verification-deep-dive.md)。

## 许可证

MIT — 详见 [LICENSE](./LICENSE)
