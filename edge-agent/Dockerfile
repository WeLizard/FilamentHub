FROM python:3.11-alpine

ARG BUILD_VERSION=0.1.0
ARG BUILD_ARCH=amd64

LABEL io.hass.version="${BUILD_VERSION}" \
      io.hass.type="app" \
      io.hass.arch="${BUILD_ARCH}" \
      org.opencontainers.image.source="https://github.com/WeLizard/FilamentHub" \
      org.opencontainers.image.version="${BUILD_VERSION}"

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src

RUN pip install --no-cache-dir . \
    && addgroup -S filamenthub \
    && adduser -S -G filamenthub -h /app filamenthub \
    && install -d -o filamenthub -g filamenthub -m 0700 /data

ENV FH_EDGE_STATE_DIRECTORY=/data \
    PYTHONUNBUFFERED=1

VOLUME ["/data"]
# Supervisor writes root-owned 0600 options; bootstrap drops privileges before runtime I/O.
USER root

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-m", "filamenthub_edge.container", "--status"]

ENTRYPOINT ["python", "-m", "filamenthub_edge.container"]
