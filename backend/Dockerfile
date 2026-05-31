# syntax=docker/dockerfile:1.7
# Backend image. Two stages: builder installs deps into a virtualenv; runner
# copies only the venv + app. Final image runs migrations on startup (only if
# pdash.db is absent), then launches uvicorn.

FROM python:3.12-slim AS builder
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY pyproject.toml ./
# Generate a lock from pyproject; we don't ship one so this is the source of truth.
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --upgrade pip
COPY . .
RUN pip install .

FROM python:3.12-slim AS runner
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    PDASH_DATABASE_PATH=/data/pdash.db

RUN apt-get update \
 && apt-get install -y --no-install-recommends sqlite3 ca-certificates tini \
 && rm -rf /var/lib/apt/lists/* \
 && groupadd --system --gid 1000 pdash \
 && useradd --system --uid 1000 --gid pdash --home-dir /home/pdash --create-home pdash

COPY --from=builder /opt/venv /opt/venv
WORKDIR /app
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./alembic.ini
COPY docker-entrypoint.sh ./docker-entrypoint.sh
RUN chmod +x ./docker-entrypoint.sh \
 && mkdir -p /data \
 && chown -R pdash:pdash /app /data

USER pdash
EXPOSE 8080

# tini for proper signal forwarding; entrypoint runs migrations on first boot.
ENTRYPOINT ["/usr/bin/tini", "--", "./docker-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
