# ==============================================================================
# NDTM Enterprise Multi-Stage Fortified Backend Container (Unprivileged User)
# ==============================================================================
FROM python:3.12-slim-bookworm AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Final Runtime Stage
FROM python:3.12-slim-bookworm AS runner

LABEL maintainer="NDTM Systems Architecture Team <architect@ndtm.enterprise>"

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create unprivileged user (UID 10001)
RUN groupadd -g 10001 ndtmgroup && \
    useradd -u 10001 -g ndtmgroup -s /bin/bash -m ndtmuser

# Copy installed packages from builder
COPY --from=builder /root/.local /home/ndtmuser/.local
ENV PATH=/home/ndtmuser/.local/bin:$PATH
ENV PYTHONPATH=/app

# Copy application source code
COPY --chown=ndtmuser:ndtmgroup . /app
RUN mkdir -p /app/distilled_models && chown -R ndtmuser:ndtmgroup /app

USER 10001

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=5s --retries=5 --start-period=15s \
    CMD curl -f http://localhost:8000/api/v1/system/health || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2", "--log-level", "info"]
