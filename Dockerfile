FROM docker.m.daocloud.io/library/node:22-bookworm-slim AS web-builder

WORKDIR /build/web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build


FROM docker.m.daocloud.io/library/python:3.13-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    PLAYWRIGHT_CHROMIUM_EXECUTABLE=/usr/local/bin/douyin-chromium \
    HOME=/tmp \
    WEB_DIST=/app/web-dist

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src/ ./src/
RUN pip install --no-cache-dir ".[browser,worker]" \
    && playwright install --with-deps --no-shell chromium \
    && chmod -R a+rX /app /ms-playwright
RUN find /ms-playwright -path '*/chrome-linux*/chrome' -type f \
    -exec ln -s {} /usr/local/bin/douyin-chromium \; -quit \
    && test -x /usr/local/bin/douyin-chromium
COPY --from=web-builder /build/web/dist/ /app/web-dist/

EXPOSE 8099
CMD ["uvicorn", "douyin_archive.main:app", "--host", "0.0.0.0", "--port", "8099", "--proxy-headers"]
