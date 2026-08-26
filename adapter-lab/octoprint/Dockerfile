FROM octoprint/octoprint:1.11.8

WORKDIR /opt/filamenthub-bridge
COPY pyproject.toml README.md MANIFEST.in ./
COPY octoprint_filamenthub_bridge ./octoprint_filamenthub_bridge
ENV PIP_USER=false
RUN python -m pip install --no-cache-dir --no-deps .
ENV PIP_USER=true
