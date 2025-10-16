# =============================================================================
# Multi-stage Dockerfile — target-app (chaos platform)
#
# Stage 1 (builder): Compile Python wheels for all dependencies.
#                    Uses gcc + libpq-dev to build asyncpg from source.
# Stage 2 (runtime): Minimal image — copies only pre-built wheels, no compiler.
#
# Non-root user (appuser uid=1001) prevents container privilege escalation.
# If the chaos engine kills this pod, the replacement container also starts
# as a non-root user, so a container escape doesn't yield a root shell.
# =============================================================================

# ── Stage 1: dependency builder ───────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build

# Install C build tools needed to compile asyncpg and other native extensions
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --upgrade pip && \
    pip wheel \
        --no-cache-dir \
        --wheel-dir /wheels \
        -r requirements.txt

# ── Stage 2: minimal runtime image ───────────────────────────────────────────
FROM python:3.11-slim AS runtime

WORKDIR /app

# Only the runtime PostgreSQL library is needed — no compiler
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Install wheels built in Stage 1 (no internet access needed)
COPY --from=builder /wheels /wheels
RUN pip install \
        --no-cache-dir \
        --no-index \
        --find-links /wheels \
        /wheels/*.whl \
    && rm -rf /wheels

# Create a non-root user and group
RUN groupadd --gid 1001 appgroup && \
    useradd --uid 1001 --gid appgroup --no-create-home --shell /usr/sbin/nologin appuser

# Copy application source (owned by the non-root user)
COPY --chown=appuser:appgroup app/ ./app/

# Switch to non-root before any further commands
USER appuser

EXPOSE 8000

# Health check mirrors the Kubernetes liveness probe configuration
# start-period gives the app time to complete DB init and seed on first start
HEALTHCHECK \
    --interval=30s \
    --timeout=10s \
    --start-period=60s \
    --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

# Single Uvicorn worker per container — horizontal scaling handled by HPA.
# Use --workers 1 so Prometheus metrics are consistent per pod (multi-process
# Prometheus requires shared memory which complicates the setup).
CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "1", \
     "--log-level", "warning"]
