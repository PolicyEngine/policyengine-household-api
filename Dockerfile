# Multi-stage build for security and minimal size
FROM python:3.13-slim AS builder

# Set working directory
WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    make \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY setup.py .
COPY policyengine_household_api/__init__.py policyengine_household_api/
RUN pip install --no-cache-dir --user --upgrade pip setuptools wheel

# Install dependencies
COPY . .
RUN pip install --no-cache-dir --user -e .

# Final stage - hardened runtime image
FROM python:3.13-slim

# Security: Create non-root user
RUN groupadd -r appuser && useradd -r -g appuser -u 1000 appuser

# Install runtime dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Set working directory
WORKDIR /app

# Copy Python packages from builder
COPY --from=builder --chown=appuser:appuser /root/.local /home/appuser/.local

# Copy application code
COPY --chown=appuser:appuser . /app

# Update PATH for user-installed packages
ENV PATH=/home/appuser/.local/bin:$PATH
ENV PYTHONPATH=/app:$PYTHONPATH

# Security: Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Security: Drop all capabilities
RUN setcap -r /usr/local/bin/python3.13 2>/dev/null || true

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/')" || exit 1

# Switch to non-root user
USER appuser

# Expose port (informational)
EXPOSE 8080

# Run the application with gunicorn for production
ENV PORT=8080
CMD ["gunicorn", "-b", ":8080", "policyengine_household_api.api", "--timeout", "300", "--workers", "2"]