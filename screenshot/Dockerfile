# syntax=docker/dockerfile:1.7
# Screenshot sidecar. Installs the app + a matching Chromium via Playwright.
# This image is large (~1GB) because it bundles a headless browser; that is the
# cost of real pixel-accurate dashboard screenshots and is why it lives in its
# own service rather than the lean backend image.

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /app
COPY pyproject.toml README.md ./
COPY app ./app

# Install the package, then the Chromium build matching the installed Playwright
# (--with-deps pulls the required OS libraries).
RUN pip install --upgrade pip \
 && pip install . \
 && playwright install --with-deps chromium

EXPOSE 9000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "9000"]
