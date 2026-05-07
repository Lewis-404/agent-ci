"""Fact Checker — verifies agent claims by re-checking facts independently."""

from pathlib import Path

import httpx

from agent_ci.checkers.base import BaseChecker
from agent_ci.types import CheckerReport, CheckResult, Severity


class FactChecker(BaseChecker):
    """Independently verifies agent claims: file existence, API responses, LLM judging."""

    name = "fact"

    async def verify(self, output_dir: Path) -> CheckerReport:
        report = CheckerReport(checker_name=self.name)
        config = self.config.get("fact", {})

        file_checks = config.get("files", [])
        for file_check in file_checks:
            report.checks.extend(self._check_files(output_dir, file_check))

        api_checks = config.get("api", [])
        for api_check in api_checks:
            report.checks.append(await self._check_api(api_check))

        llm_checks = config.get("llm_judge", [])
        for llm_check in llm_checks:
            report.checks.append(await self._llm_judge(output_dir, llm_check))

        return report

    def _check_files(self, output_dir: Path, spec: dict) -> list[CheckResult]:
        results: list[CheckResult] = []
        pattern = spec.get("pattern", "*")
        expected_count = spec.get("expected_count")
        min_size = spec.get("min_size_bytes")

        matches = list(output_dir.glob(pattern))

        if expected_count is not None:
            if len(matches) == expected_count:
                results.append(
                    CheckResult(
                        checker=self.name,
                        check_name="fact:file_count",
                        severity=Severity.PASS,
                        message=(
                            f"File count matches: {len(matches)} files for "
                            f"'{pattern}'"
                        ),
                    )
                )
            else:
                matched_files = [
                    str(match.relative_to(output_dir)) for match in matches[:10]
                ]
                results.append(
                    CheckResult(
                        checker=self.name,
                        check_name="fact:file_count",
                        severity=Severity.FAIL,
                        message=(
                            f"Expected {expected_count} files for '{pattern}', "
                            f"found {len(matches)}"
                        ),
                        detail=f"Files: {matched_files}",
                    )
                )

        if min_size and matches:
            for file_path in matches:
                size = file_path.stat().st_size
                if size < min_size:
                    relative_path = file_path.relative_to(output_dir)
                    results.append(
                        CheckResult(
                            checker=self.name,
                            check_name="fact:file_size",
                            severity=Severity.WARN,
                            message=(
                                f"File below min size ({min_size}B): "
                                f"{relative_path} ({size}B)"
                            ),
                            file_path=str(file_path),
                        )
                    )

        content_checks = spec.get("content_checks", [])
        for content_check in content_checks:
            for file_path in matches:
                try:
                    content = file_path.read_text(encoding="utf-8")
                except UnicodeDecodeError:
                    continue

                check_type = content_check.get("type")
                needle = content_check.get("value", "")
                relative_path = file_path.relative_to(output_dir)

                if check_type == "contains":
                    if needle in content:
                        results.append(
                            CheckResult(
                                checker=self.name,
                                check_name="fact:content_contains",
                                severity=Severity.PASS,
                                message=(
                                    f"Content check passed: '{needle}' found in "
                                    f"{relative_path}"
                                ),
                            )
                        )
                    else:
                        results.append(
                            CheckResult(
                                checker=self.name,
                                check_name="fact:content_contains",
                                severity=Severity.FAIL,
                                message=(
                                    f"Content check failed: '{needle}' not found in "
                                    f"{relative_path}"
                                ),
                                file_path=str(file_path),
                            )
                        )
                elif check_type == "not_contains":
                    if needle not in content:
                        results.append(
                            CheckResult(
                                checker=self.name,
                                check_name="fact:content_not_contains",
                                severity=Severity.PASS,
                                message=(
                                    f"Content check passed: '{needle}' absent from "
                                    f"{relative_path}"
                                ),
                            )
                        )
                    else:
                        results.append(
                            CheckResult(
                                checker=self.name,
                                check_name="fact:content_not_contains",
                                severity=Severity.FAIL,
                                message=(
                                    f"Forbidden content found: '{needle}' in "
                                    f"{relative_path}"
                                ),
                                file_path=str(file_path),
                            )
                        )

        return results

    async def _check_api(self, spec: dict) -> CheckResult:
        endpoint = spec.get("endpoint", "")
        method = spec.get("method", "GET").upper()
        expected_status = spec.get("expected_status", 200)
        timeout = spec.get("timeout", 10)
        request_body = spec.get("body", {})

        if not endpoint:
            return CheckResult(
                checker=self.name,
                check_name="fact:api",
                severity=Severity.WARN,
                message="API check skipped: no endpoint specified",
            )

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                if method == "GET":
                    response = await client.get(endpoint)
                elif method == "POST":
                    response = await client.post(endpoint, json=request_body)
                else:
                    response = await client.request(
                        method,
                        endpoint,
                        json=request_body,
                    )

                status_ok = response.status_code == expected_status
                severity = Severity.PASS if status_ok else Severity.FAIL

                detail = f"Status: {response.status_code} (expected {expected_status})"
                if not status_ok:
                    detail += f"\nBody: {response.text[:200]}"

                return CheckResult(
                    checker=self.name,
                    check_name="fact:api",
                    severity=severity,
                    message=(
                        f"API check: {method} {endpoint} → {response.status_code}"
                    ),
                    detail=detail,
                )
        except httpx.TimeoutException:
            return CheckResult(
                checker=self.name,
                check_name="fact:api",
                severity=Severity.FAIL,
                message=f"API timeout: {method} {endpoint}",
                detail=f"Request timed out after {timeout}s",
            )
        except Exception as error:
            return CheckResult(
                checker=self.name,
                check_name="fact:api",
                severity=Severity.FAIL,
                message=f"API error: {method} {endpoint}",
                detail=str(error),
            )

    async def _llm_judge(self, output_dir: Path, spec: dict) -> CheckResult:
        """Use an independent LLM to evaluate an agent's claim.

        Requires openai or litellm to be installed.
        """
        file_pattern = spec.get("file")
        rubric = spec.get("rubric", "")
        model = spec.get("model", "deepseek-v4-flash")

        if not file_pattern:
            return CheckResult(
                checker=self.name,
                check_name="fact:llm_judge",
                severity=Severity.WARN,
                message="LLM judge skipped: no file specified",
            )

        files = list(output_dir.glob(file_pattern))
        if not files:
            return CheckResult(
                checker=self.name,
                check_name="fact:llm_judge",
                severity=Severity.FAIL,
                message=f"LLM judge: no files matched '{file_pattern}'",
            )

        target_file = files[0]
        try:
            content = target_file.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return CheckResult(
                checker=self.name,
                check_name="fact:llm_judge",
                severity=Severity.WARN,
                message=(
                    "LLM judge: cannot read "
                    f"{target_file.relative_to(output_dir)}"
                ),
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
            severity_map = {
                "PASS": Severity.PASS,
                "WARN": Severity.WARN,
                "FAIL": Severity.FAIL,
            }
            severity = severity_map.get(verdict_str, Severity.WARN)

            return CheckResult(
                checker=self.name,
                check_name="fact:llm_judge",
                severity=severity,
                message=(
                    f"LLM judge verdict: {verdict_str} — "
                    f"{target_file.relative_to(output_dir)}"
                ),
                detail=f"Model: {model}\nReason: {reason}",
                file_path=str(target_file.relative_to(output_dir)),
            )
        except Exception as error:
            return CheckResult(
                checker=self.name,
                check_name="fact:llm_judge",
                severity=Severity.WARN,
                message=f"LLM judge failed: {error}",
                detail=(
                    "Install 'openai' or 'litellm' with: "
                    "pip install agent-ci-verify[llm]"
                ),
            )

    async def _call_llm(self, prompt: str, model: str) -> str:
        """Call LLM API, trying openai first, then litellm.

        Supports: OPENAI_API_KEY, DEEPSEEK_API_KEY env vars.
        Config keys: api_key, base_url in fact.llm_judge spec or top-level llm config.
        """
        import os

        llm_config = self.config.get("llm", {})
        api_key = (
            llm_config.get("api_key")
            or os.environ.get("OPENAI_API_KEY")
            or os.environ.get("DEEPSEEK_API_KEY")
        )
        base_url = (
            llm_config.get("base_url")
            or os.environ.get("OPENAI_BASE_URL")
            or os.environ.get("DEEPSEEK_BASE_URL")
        )

        try:
            from openai import AsyncOpenAI

            client_kwargs = {}
            if api_key:
                client_kwargs["api_key"] = api_key
            if base_url:
                client_kwargs["base_url"] = base_url

            client = AsyncOpenAI(**client_kwargs)
            response = await client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
                max_tokens=200,
            )
            return response.choices[0].message.content or ""
        except ImportError:
            pass
        except Exception as error:
            if api_key:
                raise RuntimeError(f"LLM call failed: {error}") from error

        try:
            import litellm

            response = await litellm.acompletion(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
                max_tokens=200,
            )
            return response.choices[0].message.content or ""
        except ImportError as error:
            raise RuntimeError(
                "Neither openai nor litellm is installed. "
                "Install with: pip install 'agent-ci-verify[llm]'"
            ) from error

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
