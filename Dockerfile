# Production image (Render). Local development uses backend/Dockerfile via docker compose.
#
# Stage 1 builds the React app with Node. Stage 2 is a slim Python image that gets only the
# built files, so Node and node_modules never ship to production.

# ---- Stage 1: build the frontend ---------------------------------------------------------
FROM node:20-alpine AS web
WORKDIR /web
# Lockfile first: Docker reuses the npm ci layer until dependencies change.
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---- Stage 2: the API, serving the built frontend ----------------------------------------
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    APP_ENV=production \
    STATIC_DIR=/app/static
WORKDIR /app

# Runtime dependencies only (no pytest/ruff in production).
COPY backend/requirements.txt ./
RUN pip install -r requirements.txt

COPY backend/ ./
COPY --from=web /web/dist ./static

# Run as an unprivileged user, not root.
RUN useradd --create-home appuser && chown -R appuser /app
USER appuser

# Render sets PORT (default 10000); locally it falls back to 8000.
# Migrations run on every start: a no-op when the schema is already current.
# --forwarded-allow-ips: trust Render's proxy, so the app sees the real https scheme.
EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --forwarded-allow-ips '*'"]
