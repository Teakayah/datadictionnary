# ─── Stage 1: builder ────────────────────────────────────────────────────────
FROM python:3.15-slim AS builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        g++ \
        libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies into a prefix directory
COPY requirements.txt constraints.txt ./
RUN pip install --upgrade pip \
    && pip install --prefix=/install --no-cache-dir -c constraints.txt -r requirements.txt


# ─── Stage 2: final ──────────────────────────────────────────────────────────
FROM python:3.15-slim AS final

# Install curl for the healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Create non-root user (UID/GID 10001 matches Kubernetes pod securityContext)
RUN groupadd --gid 10001 appuser \
    && useradd --uid 10001 --gid 10001 --no-create-home --shell /bin/bash appuser

# Create app, data, and shared DuckDB extension directories
RUN mkdir -p /app /data /opt/duckdb_extensions \
    && chown appuser:appuser /app /data /opt/duckdb_extensions

WORKDIR /app

# Copy application source
COPY --chown=appuser:appuser app.py         ./app.py
COPY --chown=appuser:appuser src/           ./src/
COPY --chown=appuser:appuser scripts/       ./scripts/
COPY --chown=appuser:appuser locale/        ./locale/
COPY --chown=appuser:appuser assets/        ./assets/
COPY --chown=appuser:appuser design_system/ ./design_system/
COPY --chown=appuser:appuser .streamlit/    ./.streamlit/

ENV HOME=/tmp \
    DUCKDB_EXTENSION_DIRECTORY=/opt/duckdb_extensions

USER appuser

# Pre-cache the DuckDB vss extension for offline usage under readOnlyRootFilesystem
RUN python -c "import duckdb; con = duckdb.connect(':memory:', config={'extension_directory': '/opt/duckdb_extensions'}); con.execute('INSTALL vss;')" \
    && chmod -R a+rX /opt/duckdb_extensions

# The same image is used for three workloads:
#   - dd-app          (default CMD)              — Streamlit UI on 8501
#   - dd-sync-worker  (CMD overridden by k8s)    — `python -m src.sync.daemon` on 8765
#   - dd-api          (CMD overridden by k8s)    — uvicorn src.api.main:app on 8080
EXPOSE 8501 8765 8080

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8501/_stcore/health || exit 1

CMD ["streamlit", "run", "app.py", \
     "--server.port=8501", \
     "--server.address=0.0.0.0", \
     "--server.headless=true"]
