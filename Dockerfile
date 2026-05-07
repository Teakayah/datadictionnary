# ─── Stage 1: builder ────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        g++ \
        libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies into a prefix directory
COPY requirements.txt .
RUN pip install --upgrade pip \
    && pip install --prefix=/install --no-cache-dir -r requirements.txt


# ─── Stage 2: final ──────────────────────────────────────────────────────────
FROM python:3.11-slim AS final

# Install curl for the healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Create non-root user
RUN groupadd --gid 1000 appuser \
    && useradd --uid 1000 --gid 1000 --no-create-home --shell /bin/bash appuser

# Create app and data directories
RUN mkdir -p /app /data && chown appuser:appuser /app /data

WORKDIR /app

# Copy application source
COPY --chown=appuser:appuser app.py         ./app.py
COPY --chown=appuser:appuser src/           ./src/
COPY --chown=appuser:appuser scripts/       ./scripts/
COPY --chown=appuser:appuser locale/        ./locale/
COPY --chown=appuser:appuser assets/        ./assets/
COPY --chown=appuser:appuser design_system/ ./design_system/

USER appuser

# The same image is used for two workloads:
#   - dd-app          (default CMD)              — Streamlit UI on 8501
#   - dd-sync-worker  (CMD overridden by k8s)    — `python -m src.sync.daemon` on 8765
EXPOSE 8501 8765

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8501/_stcore/health || exit 1

CMD ["streamlit", "run", "app.py", \
     "--server.port=8501", \
     "--server.address=0.0.0.0", \
     "--server.headless=true"]
