# Build arguments let users behind slow or blocked registries point at mirrors
# without editing this file; see README "构建加速" for the China-friendly set.
ARG NODE_IMAGE=node:22-bookworm-slim
ARG PYTHON_IMAGE=python:3.13-slim-bookworm

FROM ${NODE_IMAGE} AS web-builder
ARG NPM_REGISTRY=https://registry.npmjs.org/
WORKDIR /build/web
COPY web/package.json web/package-lock.json ./
RUN npm config set registry "${NPM_REGISTRY}" && npm ci
COPY web/ ./
RUN npm run build


FROM ${PYTHON_IMAGE} AS runtime
ARG DEBIAN_MIRROR=
ARG PIP_INDEX_URL=https://pypi.org/simple
ARG PLAYWRIGHT_DOWNLOAD_HOST=
ARG APP_COMMIT=unknown

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    PLAYWRIGHT_CHROMIUM_EXECUTABLE=/usr/local/bin/douyin-chromium \
    HOME=/tmp \
    SQLITE_TMPDIR=/archive/tmp \
    WEB_DIST=/app/web-dist \
    APP_COMMIT=${APP_COMMIT}

WORKDIR /app
COPY pyproject.toml README.md ./
COPY docker/douyin_archive/ ./src/douyin_archive/
RUN if [ -n "${DEBIAN_MIRROR}" ]; then sed -i \
      -e "s|http://deb.debian.org/debian-security|${DEBIAN_MIRROR}/debian-security|g" \
      -e "s|http://deb.debian.org/debian|${DEBIAN_MIRROR}/debian|g" \
      /etc/apt/sources.list.d/debian.sources; fi
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir --index-url "${PIP_INDEX_URL}" ".[browser,worker]" \
    && PLAYWRIGHT_DOWNLOAD_HOST="${PLAYWRIGHT_DOWNLOAD_HOST}" playwright install --with-deps --no-shell chromium \
    && chmod -R a+rX /app /ms-playwright
RUN find /ms-playwright -path '*/chrome-linux*/chrome' -type f \
    -exec ln -s {} /usr/local/bin/douyin-chromium \; -quit \
    && test -x /usr/local/bin/douyin-chromium
COPY src/ ./src/
RUN pip install --no-cache-dir --no-deps --index-url "${PIP_INDEX_URL}" .
COPY --from=web-builder /build/web/dist/ /app/web-dist/

EXPOSE 8099
CMD ["uvicorn", "douyin_archive.main:app", "--host", "0.0.0.0", "--port", "8099", "--proxy-headers"]
