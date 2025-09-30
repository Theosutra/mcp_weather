# syntax=docker/dockerfile:1
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    UVICORN_WORKERS=1

WORKDIR /app

# System deps (certs, locales, curl for healthchecks)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl && \
    rm -rf /var/lib/apt/lists/*

# Install dependencies
COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copy app
COPY src ./src

# Default env (override in compose/prod)
ENV MCP_AUTH_TOKEN=""

EXPOSE 8085

# Healthcheck (simple GET /mcp)
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
 CMD curl -fsS http://127.0.0.1:8085/mcp || exit 1

CMD ["python", "-m", "uvicorn", "src.mcp_weather.mcp_sse_app:app", "--host", "0.0.0.0", "--port", "8085"]
