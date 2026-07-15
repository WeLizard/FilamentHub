FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    libpango-1.0-0 libpangocairo-1.0-0 libpangoft2-1.0-0 \
    libcairo2 libgdk-pixbuf-2.0-0 libglib2.0-0 libffi-dev \
    fonts-liberation fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

# Copy the dependency manifest alone: the layer below must depend only on
# pyproject.toml so code-only rebuilds reuse the cached dependency install.
COPY pyproject.toml ./

# Pre-install dependencies against a stub package (source is not copied yet);
# the stub itself is uninstalled, the dependency set stays in this layer.
RUN pip install --no-cache-dir --upgrade pip && \
    mkdir -p app && touch app/__init__.py && \
    pip install --no-cache-dir ".[dev]" && \
    pip uninstall -y filamenthub-backend && \
    rm -rf app

# Copy application code
COPY . .

# Editable install of the application itself; dependencies are already cached
RUN pip install --no-cache-dir --no-deps -e ".[dev]"

# Expose port
EXPOSE 8000

# Run application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
