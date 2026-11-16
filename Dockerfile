# Remote HK Criminal Law MCP: MCP + JSON API + mobile web app in one process.
#
# The corpus is not baked into the image. Mount a built SQLite database at
# /data/hk_law.db (see docs/remote-access.md) and set at least
# HK_LAW_HTTP_ACCESS_KEY or HK_LAW_HTTP_ALLOW_ANONYMOUS=1.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HK_LAW_HOME=/data \
    HK_LAW_DB=/data/hk_law.db \
    HK_LAW_HTTP_HOST=0.0.0.0 \
    HK_LAW_HTTP_PORT=8765

WORKDIR /app

COPY pyproject.toml README.md LICENSE NOTICE ./
COPY src ./src
RUN pip install .

RUN useradd --create-home --uid 10001 hklaw \
    && mkdir -p /data \
    && chown -R hklaw:hklaw /data /app

USER hklaw

EXPOSE 8765

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/healthz', timeout=3)"

# One process: the OAuth state and rate limiter are in-process, and SQLite
# writes are serialised. Scale by adding a read replica, not uvicorn workers.
CMD ["hk-law", "serve-http", "--host", "0.0.0.0", "--port", "8765"]
