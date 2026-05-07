"""Fact Checker — verifies agent claims by re-checking facts independently."""

from pathlib import Path
from typing import Any

import httpx

from agent_ci.checkers.base import BaseChecker
from agent_ci.types import CheckResult, CheckerReport, Severity


class FactChecker(BaseChecker):
    """Independently verifies agent claims: file existence, API responses, LLM judging."""

    name = "fact"

    async def verify(self, output_dir: Path) -> CheckerReport:
        report = CheckerReport(checker_name=self.name)
        config = self.config.get("fact", {})

        # 1. File existence checks
        file_checks = config.get("files", [])
        for fc in file_checks:
            report.checks.extend(self._check_files(output_dir, fc))

        # 2. API response reconciliation
        api_checks = config.get("api", [])
        for ac in api_checks:
            report.checks.append(await self._check_api(output_dir, ac))

        # 3. LLM-as-Judge (optional, requires openai or litellm)
        llm_checks = config.get("llm_judge", [])
        for lc in llm_checks:
            report.checks.append(await self._llm_judge(output_dir, lc))

        return report

    # ── File existence ─────────────────────────────────────────────

    def _check_files(self, output_dir: Path, spec: dict) -> list[CheckResult]:
        results: list[CheckResult] = []
        pattern = spec.get("pattern", "*")
        expected_count = spec.get("expected_count")
        min_size = spec.get("min_size_bytes")

        matches = list(output_dir.glob(pattern))

        if expected_count is not None:
            if len(matches) == expected_count:
                results.append(CheckResult(
                    checker=self.name, check_name="fact:file_count",
                    severity=Severity.PASS,
                    message=f"File count matches: {len(matches)} files for '{pattern}'",
                ))
            else:
                results.append(CheckResult(
                    checker=self.name, check_name="fact:file_count",
                    severity=Severity.FAIL,
                    message=f"Expected {expected_count} files for '{pattern}', found {len(matches)}",
                    detail=f"Files: {[str(m.relative_to(output_dir)) for m in matches[:10]]}",
                ))

        if min_size and matches:
            for fpath in matches:
                size = fpath.stat().st_size
                if size < min_size:
                    results.append(CheckResult(
                        checker=self.name, check_name="fact:file_size",
                        severity=Severity.WARN,
                        message=f"File below min size ({min_size}B): {fpath.relative_to(output_dir)} ({size}B)",
                        file_path=str(fpath),
                    ))

        # Content checks
        content_checks = spec.get("content_checks", [])
        for cc in content_checks:
            for fpath in matches:
                try:
                    content = fpath.read_text(encoding="utf-8")
                except UnicodeDecodeError:
                    continue
                cc_type = cc.get("type")
                if cc_type == "contains":
                    needle = cc["value"]
                    if needle in content:
                        results.append(CheckResult(
                            checker=self.name, check_name="fact:content_contains",
                            severity=Severity.PASS,
                            message=f"Content check passed: '{needle}' found in {fpath.relative_to(output_dir)}",
                        ))
                    else:
                        results.append(CheckResult(
                            checker=self.name, check_name="fact:content_contains",
                            severity=Severity.FAIL,
                            message=f"Content check failed: '{needle}' not found in {fpath.relative_to(output_dir)}",
                            file_path=str(fpath),
                        ))
                elif cc_type == "not_contains":
                    needle = cc["value"]
                    if needle not in content:
                        results.append(CheckResult(
                            checker=self.name, check_name="fact:content_not_contains",
                            severity=Severity.PASS,
                            message=f"Content check passed: '{needle}' absent from {fpath.relative_to(output_dir)}",
                        ))
                    else:
                        results.append(CheckResult(
                            checker=self.name, check_name="fact:content_not_contains",
                            severity=Severity.FAIL,
                            message=f"Forbidden content found: '{needle}' in {fpath.relative_to(output_dir)}",
                            file_path=str(fpath),
                        ))

        return results

    # ── API reconciliation ─────────────────────────────────────────

    async def _check_api(self, output_dir: Path, spec: dict) -> CheckResult:
        endpoint = spec.get("endpoint", "")
        method = spec.get("method", "GET").upper()
        expected_status = spec.get("expected_status", 200)
        timeout = spec.get("timeout", 10)

        if not endpoint:
            return CheckResult(
                checker=self.name, check_name="fact:api",
                severity=Severity.WARN,
                message="API check skipped: no endpoint specified",
            )

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                if method == "GET":
                    resp = await client.get(endpoint)
                elif method == "POST":
                    resp = await client.post(endpoint, json=spec.get("body", {}))
                else:
                    resp = await client.request(method, endpoint, json=spec.get("body", {}))

                status_ok = resp.status_code == expected_status
                severity = Severity.PASS if status_ok else Severity.FAIL

                detail = f"Status: {resp.status_code} (expected {expected_status})"
                if not status_ok:
                    detail += f"\nBody: {resp.text[:200]}"

                return CheckResult(
                    checker=self.name, check_name="fact:api",
                    severity=severity,
                    message=f"API check: {method} {endpoint} → {resp.status_code}",
                    detail=detail,
                )
        except httpx.TimeoutException:
            return CheckResult(
                checker=self.name, check_name="fact:api",
                severity=Severity.FAIL,
                message=f"API timeout: {method} {endpoint}",
                detail=f"Request timed out after {timeout}s",
            )
        except Exception as e:
            return CheckResult(
                checker=self.name, check_name="fact:api",
                severity=Severity.FAIL,
                message=f"API error: {method} {endpoint}",
                detail=str(e),
            )

    # ── LLM-as-Judge ───────────────────────────────────────────────

    async def _llm_judge(self, output_dir: Path, spec: dict) -> CheckResult:
        """Use an independent LLM to evaluate an agent's claim.

        Requires openai or litellm to be installed.
        """
        file_pattern = spec.get("file")
        claim_field = spec.get("claim_field", "content")
        rubric = spec.get("rubric", "")
        model = spec.get("model", "deepseek-v4-flash")

        if not file_pattern:
            return CheckResult(
                checker=self.name, check_name="fact:llm_judge",
                severity=Severity.WARN,
                message="LLM judge skipped: no file specified",
            )

        files = list(output_dir.glob(file_pattern))
        if not files:
            return CheckResult(
                checker=self.name, check_name="fact:llm_judge",
                severity=Severity.FAIL,
                message=f"LLM judge: no files matched '{file_pattern}'",
            )

        # Read the agent output
        target_file = files[0]
        try:
            content = target_file.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return CheckResult(
                checker=self.name, check_name="fact:llm_judge",
                severity=Severity.WARN,
                message=f"LLM judge: cannot read {target_file.relative_to(output_dir)}",
            )

        prompt = f"""You are an independent fact-checker evaluating an AI agent's output.

Rubric: {rubric}

Agent output:
{content[:4000]}

Respond in this exact format:
VERDICT: [PASS | WARN | FAIL]
REASON: [one sentence explanation]"""

        try:
            response = await self._call_llm(prompt, model)
            verdict_str, reason = self._parse_judge_response(response)

            severity_map = {"PASS": Severity.PASS, "WARN": Severity.WARN, "FAIL": Severity.FAIL}
            severity = severity_map.get(verdict_str, Severity.WARN)

            return CheckResult(
                checker=self.name, check_name="fact:llm_judge",
                severity=severity,
                message=f"LLM judge verdict: {verdict_str} — {target_file.relative_to(output_dir)}",
                detail=f"Model: {model}\nReason: {reason}",
                file_path=str(target_file.relative_to(output_dir)),
            )
        except Exception as e:
            return CheckResult(
                checker=self.name, check_name="fact:llm_judge",
                severity=Severity.WARN,
                message=f"LLM judge failed: {e}",
                detail="Install 'openai' or 'litellm' with: pip install agent-ci[llm]",
            )

    async def _call_llm(self, prompt: str, model: str) -> str:
        """Call LLM API, trying openai first, then litellm.

        Supports: OPENAI_API_KEY, DEEPSEEK_API_KEY env vars.
        Config keys: api_key, base_url in fact.llm_judge spec or top-level llm config.
        """
        import os

        llm_config = self.config.get("llm", {})
        api_key = llm_config.get("api_key") or os.environ.get("OPENAI_API_KEY") or os.environ.get("DEEPSEEK_API_KEY")
        base_url = llm_config.get("base_url") or os.environ.get("OPENAI_BASE_URL") or os.environ.get("DEEPSEEK_BASE_URL")

        # Try openai
        try:
            from openai import AsyncOpenAI
            client_kwargs = {}
            if api_key:
                client_kwargs["api_key"] = api_key
            if base_url:
                client_kwargs["base_url"] = base_url
            client = AsyncOpenAI(**client_kwargs)
            resp = await client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
                max_tokens=200,
            )
            return resp.choices[0].message.content or ""
        except ImportError:
            pass
        except Exception as e:
            # If openai failed with explicit key, don't fall through silently
            if api_key:
                raise RuntimeError(f"LLM call failed: {e}") from e

        # Try litellm
        try:
            import litellm
            resp = await litellm.acompletion(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
                max_tokens=200,
            )
            return resp.choices[0].message.content or ""
        except ImportError:
            raise RuntimeError(
                "Neither openai nor litellm is installed. "
                "Install with: pip install 'agent-ci[llm]'"
            )

    @staticmethod
    def _parse_judge_response(response: str) -> tuple[str, str]:
        """Parse VERDICT and REASON from LLM response."""
        verdict = "WARN"
        reason = "Could not parse judge response"
        for line in response.strip().split("\n"):
            if line.upper().startswith("VERDICT:"):
                verdict = line.split(":", 1)[1].strip().upper()
            elif line.upper().startswith("REASON:"):
                reason = line.split(":", 1)[1].strip()
        return verdict, reason
