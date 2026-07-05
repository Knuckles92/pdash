# syntax=docker/dockerfile:1.7
# MCP server image. Single-stage; the package is small.

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates tini \
 && rm -rf /var/lib/apt/lists/* \
 && groupadd --system --gid 1000 pdash \
 && useradd --system --uid 1000 --gid pdash --home-dir /home/pdash --create-home pdash

WORKDIR /app
COPY pyproject.toml ./
COPY app ./app
RUN pip install --upgrade pip && pip install .

USER pdash
EXPOSE 8090

# Required env: PDASH_SERVICE_SECRET (mints internal-API auth) and
# PDASH_BACKEND_URL (e.g. http://backend:8080). See .env.example.
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["python", "-m", "app.main"]
