"""HTTP API server for agent-ci-verify — continuous verification service."""

import os
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
        from fastapi import FastAPI, HTTPException
        from fastapi.responses import JSONResponse
        from pydantic import BaseModel
    except ImportError as import_error:
        raise ImportError(
            "FastAPI is required for server mode. "
            "Install with: pip install 'agent-ci-verify[server]'"
        ) from import_error

    class VerifyRequest(BaseModel):
        """Request body for POST /verify."""

        output_directory: str
        config_file: str | None = None

    application = FastAPI(
        title="agent-ci-verify",
        description="CI/CD verification pipeline for AI agent outputs",
        version=__version__,
    )

    @application.get("/health")
    async def health_check() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    @application.post("/verify")
    async def verify_output(request_body: VerifyRequest) -> JSONResponse:
        """Verify agent output directory and return the pipeline report."""
        output_dir = Path(request_body.output_directory)

        # ── Server mode security ─────────────────────────────────
        # Client-supplied config_file is ignored in server mode —
        # always use the server's own config to prevent path injection.
        # Directory-based plugins are disabled (config.py strips them).
        # Output directory is restricted to allowed_roots / workspace.
        # ──────────────────────────────────────────────────────────

        if not output_dir.exists():
            raise HTTPException(
                status_code=400,
                detail=f"Output directory not found: {request_body.output_directory}",
            )

        if not output_dir.is_dir():
            raise HTTPException(
                status_code=400,
                detail=(
                    "Path is not a directory. "
                    "Server mode only accepts directories within the workspace."
                ),
            )

        try:
            config = load_config(server_mode=True)
        except Exception as error:
            raise HTTPException(
                status_code=500,
                detail=f"Config error: {error}",
            ) from error

        # Restrict output_dir to workspace
        workspace = _resolve_workspace(config)
        resolved = output_dir.resolve()
        if not str(resolved).startswith(str(workspace.resolve())):
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Output directory is outside the workspace: "
                    f"{request_body.output_directory}"
                ),
            )

        report: PipelineReport = await run_pipeline(output_dir, config)
        response_data = report.to_dict()

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
