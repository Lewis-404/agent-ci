"""HTTP API server for agent-ci-verify — continuous verification service."""

import hashlib
import os
import secrets
import threading
import time
import uuid
from collections import defaultdict
from pathlib import Path
from typing import Any

from agent_ci import __version__
from agent_ci.config import load_config
from agent_ci.pipeline import run_pipeline
from agent_ci.types import PipelineReport


def create_app(config_path: str | None = None) -> Any:
    """Build a FastAPI application with /verify and /health endpoints.

    Args:
        config_path: Optional path to .agent-ci.yaml. Falls back to auto-discovery.

    Returns:
        A FastAPI application instance.

    """
    try:
        from fastapi import Depends, FastAPI, Header, HTTPException, Request
        from fastapi.responses import JSONResponse
        from pydantic import BaseModel
    except ImportError as import_error:
        raise ImportError(
            "FastAPI is required for server mode. "
            "Install with: pip install 'agent-ci-verify[server]'"
        ) from import_error

    try:
        import structlog

        logger = structlog.get_logger("agent-ci-verify")
        _has_structlog = True
    except ImportError:
        import logging

        logger = logging.getLogger("agent-ci-verify")  # type: ignore[assignment]
        _has_structlog = False

    def _read_rate_limit(name: str, default: int | float) -> int | float:
        raw_value = os.environ.get(name, str(default))
        parser = int if isinstance(default, int) else float
        try:
            value = parser(raw_value)
        except ValueError:
            if _has_structlog:
                logger.warning(
                    "invalid rate-limit setting",
                    setting=name,
                    fallback=default,
                )
            else:
                logger.warning("invalid rate-limit setting: %s", name)
            return default
        if value <= 0:
            if _has_structlog:
                logger.warning(
                    "non-positive rate-limit setting",
                    setting=name,
                    fallback=default,
                )
            else:
                logger.warning("non-positive rate-limit setting: %s", name)
            return default
        return value

    # ── Rate limiter ───────────────────────────────────────────────
    _rate_window: dict[str, list[float]] = defaultdict(list)
    _rate_window_guard = threading.Lock()
    _last_rate_window_sweep = 0.0

    def _rate_limit_identity(identity: str, limit: int, window: float) -> bool:
        """Return True if the identity is within limit; False if exceeded."""
        nonlocal _last_rate_window_sweep
        now = time.time()
        with _rate_window_guard:
            if now - _last_rate_window_sweep >= window:
                stale_identities = [
                    key
                    for key, timestamps in _rate_window.items()
                    if not timestamps or timestamps[-1] < now - window
                ]
                for stale_identity in stale_identities:
                    _rate_window.pop(stale_identity, None)
                _last_rate_window_sweep = now

            requests = _rate_window[identity]
            while requests and requests[0] < now - window:
                requests.pop(0)
            if not requests:
                _rate_window.pop(identity, None)
                requests = _rate_window[identity]
            if len(requests) >= limit:
                return False
            requests.append(now)
            return True

    # ── Pydantic models ────────────────────────────────────────────

    class VerifyRequest(BaseModel):
        """Request body for POST /verify."""

        output_directory: str
        config_file: str | None = None

    # ── Dependencies ───────────────────────────────────────────────

    def _require_api_key(
        request: Request,
        x_api_key: str = Header(None, alias="X-API-Key"),
    ) -> None:
        """FastAPI dependency: require a configured API key for all /verify requests."""
        expected = os.environ.get("AGENT_CI_API_KEY", "")
        if expected and secrets.compare_digest(x_api_key or "", expected):
            return

        client_ip = request.client.host if request.client else "unknown"
        auth_failure_identity = f"auth-fail:{client_ip}"
        if not _rate_limit_identity(auth_failure_identity, rate_limit, rate_window):
            raise HTTPException(
                status_code=429,
                detail=(
                    f"Rate limit exceeded: {rate_limit} requests "
                    f"per {int(rate_window)}s"
                ),
            )
        raise HTTPException(status_code=401, detail="Invalid or missing API key")

    def _enforce_rate_limit(
        request: Request,
        x_api_key: str = Header(None, alias="X-API-Key"),
        _: None = Depends(_require_api_key),
    ) -> None:
        client_ip = request.client.host if request.client else "unknown"
        api_key_hash = hashlib.sha256((x_api_key or "").encode("utf-8")).hexdigest()
        identity = f"{client_ip}:{api_key_hash}"
        if not _rate_limit_identity(identity, rate_limit, rate_window):
            raise HTTPException(
                status_code=429,
                detail=(
                    f"Rate limit exceeded: {rate_limit} requests "
                    f"per {int(rate_window)}s"
                ),
            )

    # ── Application ────────────────────────────────────────────────

    application = FastAPI(
        title="agent-ci-verify",
        description="CI/CD verification pipeline for AI agent outputs",
        version=__version__,
    )

    # ── Middleware: request logging ────────────────────────────────

    @application.middleware("http")
    async def log_requests(request: Request, call_next: Any) -> Any:
        request_id = str(uuid.uuid4())[:8]
        start = time.perf_counter()

        response = await call_next(request)

        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        log_kwargs = {
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "status": response.status_code,
            "duration_ms": duration_ms,
            "client": request.client.host if request.client else "unknown",
        }

        if _has_structlog:
            logger.info("request completed", **log_kwargs)
        else:
            logger.info("request completed: %s", log_kwargs)

        return response

    # ── Rate limiting ──────────────────────────────────

    rate_limit = int(_read_rate_limit("AGENT_CI_RATE_LIMIT", 10))
    rate_window = float(_read_rate_limit("AGENT_CI_RATE_WINDOW", 60.0))

    # ── Endpoints ──────────────────────────────────────────────────

    @application.get("/health")
    async def health_check() -> dict[str, Any]:
        """Health check with checker initialization verification."""
        result: dict[str, Any] = {"status": "ok", "version": __version__}
        try:
            from agent_ci.checkers.diff import DiffChecker
            from agent_ci.checkers.fact import FactChecker
            from agent_ci.checkers.schema import SchemaChecker

            checkers_status: dict[str, str] = {}
            for name, checker_cls in [
                ("schema", SchemaChecker),
                ("fact", FactChecker),
                ("diff", DiffChecker),
            ]:
                try:
                    checker_cls()
                    checkers_status[name] = "healthy"
                except Exception as error:
                    if _has_structlog:
                        logger.warning(
                            "checker health check failed",
                            checker=name,
                            error_type=type(error).__name__,
                        )
                    else:
                        logger.warning(
                            "checker health check failed: %s (%s)",
                            name,
                            type(error).__name__,
                        )
                    checkers_status[name] = "unhealthy"
                    result["status"] = "degraded"

            result["checkers"] = checkers_status
        except ImportError:
            result["status"] = "degraded"
            result["checkers"] = "unavailable"
        except Exception as error:
            if _has_structlog:
                logger.warning(
                    "checker import failed",
                    error_type=type(error).__name__,
                )
            else:
                logger.warning("checker import failed: %s", type(error).__name__)
            result["status"] = "degraded"
            result["checkers"] = "unavailable"

        return result

    @application.post("/verify", dependencies=[Depends(_enforce_rate_limit)])
    async def verify_output(request_body: VerifyRequest) -> JSONResponse:
        """Verify agent output directory and return the pipeline report."""
        output_dir = Path(request_body.output_directory)

        # ── Server mode security ─────────────────────────────────
        # Client-supplied config_file is ignored in server mode —
        # always use the server's own config to prevent path injection.
        # Directory-based plugins are disabled (config.py strips them).
        # Output directory is restricted to allowed_roots / workspace.
        # ──────────────────────────────────────────────────────────

        try:
            config = load_config(config_path, server_mode=True)
        except Exception as error:
            if _has_structlog:
                logger.warning(
                    "config load failed",
                    error_type=type(error).__name__,
                )
            else:
                logger.warning("config load failed: %s", type(error).__name__)
            raise HTTPException(
                status_code=500,
                detail="Config error",
            ) from None

        # Restrict output_dir to workspace
        try:
            workspace = _resolve_workspace(config).resolve()
        except (OSError, RuntimeError):
            raise HTTPException(
                status_code=400,
                detail="Invalid workspace path",
            ) from None
        try:
            resolved = output_dir.resolve()
        except (OSError, RuntimeError):
            raise HTTPException(
                status_code=400,
                detail="Invalid output directory path",
            ) from None
        try:
            resolved.relative_to(workspace)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Output directory is outside the workspace: "
                    f"{request_body.output_directory}"
                ),
            ) from None

        if not resolved.exists():
            raise HTTPException(
                status_code=400,
                detail=f"Output directory not found: {request_body.output_directory}",
            )

        if not resolved.is_dir():
            raise HTTPException(
                status_code=400,
                detail=(
                    "Path is not a directory. "
                    "Server mode only accepts directories within the workspace."
                ),
            )

        report: PipelineReport = await run_pipeline(resolved, config)
        response_data = report.to_dict()

        if _has_structlog:
            logger.info(
                "verification completed",
                verdict=report.verdict.value,
                checks=response_data.get("summary", {}).get("total_checks", 0),
            )

        return JSONResponse(content=response_data)

    return application


def _resolve_workspace(config: dict[str, Any]) -> Path:
    """Resolve the workspace root for server mode path restrictions.

    Priority: server.allowed_roots[0] → AGENT_CI_ALLOWED_ROOTS → cwd.
    """
    roots = config.get("server", {}).get("allowed_roots", [])
    if not roots:
        env_roots = os.environ.get("AGENT_CI_ALLOWED_ROOTS", "")
        if env_roots:
            roots = [root.strip() for root in env_roots.split(",") if root.strip()]
    if roots:
        return Path(roots[0])
    return Path.cwd()
