# syntax=docker/dockerfile:1
# HomeKeep application image (C1). Built for linux/arm64: `make build`.

# --- Stage 1: web client bundle ------------------------------------------------
FROM node:24-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

# --- Stage 2: Python dependencies from the committed lock ----------------------
FROM python:3.12-slim AS deps
COPY --from=ghcr.io/astral-sh/uv:0.13.1 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv
WORKDIR /src
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-dev --no-install-project

# --- Stage 3: runtime ------------------------------------------------------------
FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:${PATH}" \
    PORT=8000
RUN groupadd --system --gid 10001 homekeep \
    && useradd --system --uid 10001 --gid 10001 --no-create-home \
       --home-dir /nonexistent --shell /usr/sbin/nologin homekeep
WORKDIR /srv
COPY --from=deps /opt/venv /opt/venv
COPY app/ ./app/
COPY catalog_data/ ./catalog_data/
COPY fixtures/ ./fixtures/
COPY --from=web /web/dist ./web/dist
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + (os.environ.get('PORT') or '8000') + '/healthz', timeout=4)"]
# Exactly one worker: the per-process attestation key depends on it (TDD §5.3, §11.3).
# Uvicorn trusts X-Forwarded-* only from 127.0.0.1 (its default), so behind the ALB the request
# URL stays http://… and a direct caller cannot spoof it. Every public URL (OAuth callbacks,
# Protected Resource Metadata, WWW-Authenticate resource_metadata) must be built from
# APP_BASE_URL, never from the request (docs/infra-contract.md §8).
CMD ["sh", "-c", "exec uvicorn --factory app.main:create_app --host 0.0.0.0 --port \"${PORT:-8000}\" --workers 1 --proxy-headers"]
