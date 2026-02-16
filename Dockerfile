FROM python:3.12-slim AS base

LABEL maintainer="Tanaguru"
LABEL description="NVDA MCP Server - AI-powered screen reader control via MCP"

WORKDIR /app

# Install only runtime dependencies
COPY nvda_mcp/pyproject.toml /app/nvda_mcp/
RUN pip install --no-cache-dir "mcp>=1.0.0"

# Copy application code
COPY nvda_mcp/ /app/nvda_mcp/

# Default env: bridge running on Docker host
ENV NVDA_BRIDGE_URL=http://host.docker.internal:8765

# Expose SSE transport port
EXPOSE 8080

# Default: run MCP server in SSE mode (reachable from outside the container)
CMD ["python", "-m", "nvda_mcp", "--transport", "sse", "--host", "0.0.0.0", "--port", "8080"]
