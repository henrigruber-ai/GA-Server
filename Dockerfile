# File: Dockerfile
# Version: 0.1.0
# Date: 2026-08-03
# Purpose: Builds the non-root GA-Server production container.

FROM python:3.12-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build
COPY pyproject.toml VERSION README.md ./
COPY app ./app
RUN python -m pip wheel --wheel-dir /wheels .

FROM python:3.12-slim

ARG APP_UID=10001
ARG APP_GID=10001
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    GA_DATABASE_URL=sqlite:////data/ga-server.db

RUN groupadd --gid "${APP_GID}" ga-server \
    && useradd --uid "${APP_UID}" --gid "${APP_GID}" --no-create-home ga-server \
    && mkdir -p /data /app \
    && chown -R ga-server:ga-server /data /app

WORKDIR /app
COPY --from=builder /wheels /wheels
RUN python -m pip install --no-cache-dir /wheels/* && rm -rf /wheels
COPY --chown=ga-server:ga-server VERSION CHANGELOG.md alembic.ini ./
COPY --chown=ga-server:ga-server migrations ./migrations

USER ga-server
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/ready', timeout=3)"]

CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips=172.16.0.0/12"]
