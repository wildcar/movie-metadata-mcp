# syntax=docker/dockerfile:1.7
FROM python:3.12-slim AS base

# System config
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

# Install uv (pinned)
COPY --from=ghcr.io/astral-sh/uv:0.11.7 /uv /uvx /usr/local/bin/

WORKDIR /app

# Dependency resolution layer — cached across code changes.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

# Application layer.
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# Drop privileges.
RUN useradd --system --uid 10001 --home-dir /app app \
    && mkdir -p /app/.cache \
    && chown -R app:app /app
USER app

ENV PATH="/app/.venv/bin:${PATH}"

# Default transport is stdio; the container is typically attached via an
# MCP client (Claude Desktop, Inspector). Override MCP_TRANSPORT=sse for HTTP.
ENTRYPOINT ["movie-metadata-mcp"]
