FROM python:3.12-slim

LABEL org.opencontainers.image.title="jarvis-backend" \
      org.opencontainers.image.description="JARVIS AI Platform Backend" \
      org.opencontainers.image.version="3.0.0"

# Install system dependencies (bwrap for sandboxing, curl for health checks)
RUN apt-get update && apt-get install -y --no-install-recommends \
    bubblewrap \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first (better layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create data directory
RUN mkdir -p /app/data/audit /app/data/conversations

# Non-root user for security (matches Codex's process-hardening approach)
RUN useradd -m -s /bin/bash jarvis \
    && chown -R jarvis:jarvis /app/data
USER jarvis

EXPOSE 8000 50051

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=5)"

CMD ["python", "-m", "jarvis_backend.main"]
