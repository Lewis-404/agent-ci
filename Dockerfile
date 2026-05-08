# ── Agent-CI-Verify Docker Image ───────────────────────────────────
# Build:  docker build -t agent-ci-verify .
# Run:    docker run -p 8899:8899 agent-ci-verify
#
# Or use docker-compose:  docker compose up -d

FROM python:3.11-slim

LABEL org.opencontainers.image.title="agent-ci-verify"
LABEL org.opencontainers.image.description="CI/CD verification pipeline for AI agent outputs"
LABEL org.opencontainers.image.url="https://github.com/Lewis-404/agent-ci-verify"

# ── System deps ────────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# ── App user ───────────────────────────────────────────────────────
RUN useradd --create-home --shell /bin/bash appuser

# ── Install ────────────────────────────────────────────────────────
WORKDIR /app
COPY . .
RUN pip install --no-cache-dir '.[server]'

# ── Runtime ────────────────────────────────────────────────────────
USER appuser
EXPOSE 8899

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -sf http://localhost:8899/health || exit 1

ENTRYPOINT ["agent-ci"]
CMD ["--serve", "--host", "0.0.0.0", "--port", "8899"]
