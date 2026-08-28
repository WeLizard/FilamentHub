FROM python:3.11-alpine

ARG BUILD_VERSION=0.1.0
ARG BUILD_ARCH=amd64

LABEL io.hass.version="${BUILD_VERSION}" \
      io.hass.type="app" \
      io.hass.arch="${BUILD_ARCH}"

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src

RUN pip install --no-cache-dir . \
    && addgroup -S filamenthub \
    && adduser -S -G filamenthub -h /app filamenthub \
    && install -d -o filamenthub -g filamenthub -m 0700 /data

ENV FH_EDGE_STATE_PATH=/data/edge-state.json \
    PYTHONUNBUFFERED=1

VOLUME ["/data"]
USER filamenthub

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["filamenthub-edge", "--status"]

ENTRYPOINT ["filamenthub-edge"]
