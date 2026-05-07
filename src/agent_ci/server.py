"""HTTP API server for agent-ci-verify — continuous verification service."""

from pathlib import Path
from typing import Any

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
        version="1.0.0",
    )

    @application.get("/health")
    async def health_check() -> dict[str, str]:
        return {"status": "ok", "version": "1.0.0"}

    @application.post("/verify")
    async def verify_output(request_body: VerifyRequest) -> JSONResponse:
        """Verify agent output directory and return the pipeline report."""
        resolved_config_path = request_body.config_file or config_path
        output_dir = Path(request_body.output_directory)

        if not output_dir.exists():
            raise HTTPException(
                status_code=400,
                detail=f"Output directory not found: {request_body.output_directory}",
            )

        try:
            config = load_config(
                Path(resolved_config_path) if resolved_config_path else None
            )
        except FileNotFoundError as error:
            raise HTTPException(
                status_code=422,
                detail=f"Config file not found: {error}",
            ) from error
        except Exception as error:
            raise HTTPException(
                status_code=500,
                detail=f"Config error: {error}",
            ) from error

        report: PipelineReport = await run_pipeline(output_dir, config)
        response_data = report.to_dict()

        return JSONResponse(content=response_data)

    return application
