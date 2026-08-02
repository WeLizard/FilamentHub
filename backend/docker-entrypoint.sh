#!/bin/bash
set -e

echo "🚀 Starting FilamentHub backend..."

# Wait for PostgreSQL to be ready using Python
echo "⏳ Waiting for PostgreSQL..."
python << 'EOF'
import asyncio
import sys
import os
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

async def check_db():
    max_retries = 30
    retry_delay = 1
    # Формируем DATABASE_URL с правильным экранированием пароля
    from urllib.parse import quote_plus
    postgres_user = os.getenv("POSTGRES_USER", "filamenthub")
    postgres_password = os.getenv("POSTGRES_PASSWORD", "filamenthub")
    postgres_host = os.getenv("POSTGRES_HOST", "postgres")
    postgres_port = os.getenv("POSTGRES_PORT", "5432")
    postgres_db = os.getenv("POSTGRES_DB", "filamenthub")
    # URL-encode пароль для безопасной подстановки в URL
    encoded_password = quote_plus(postgres_password)
    database_url = f"postgresql+asyncpg://{postgres_user}:{encoded_password}@{postgres_host}:{postgres_port}/{postgres_db}"
    
    for attempt in range(max_retries):
        try:
            engine = create_async_engine(database_url, echo=False)
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            await engine.dispose()
            print("✅ PostgreSQL is ready!")
            sys.exit(0)
        except Exception as e:
            if attempt < max_retries - 1:
                print(f"PostgreSQL is unavailable (attempt {attempt + 1}/{max_retries}) - sleeping...")
                await asyncio.sleep(retry_delay)
            else:
                print(f"❌ Failed to connect to PostgreSQL after {max_retries} attempts: {e}")
                sys.exit(1)

asyncio.run(check_db())
EOF

# Refuse to start a new API image against an older schema. Production
# migrations are applied by scripts/deploy.sh with the newly built image before
# Compose switches the running backend. This guard protects manual `compose up`
# and other paths that bypass the deployment worker.
echo "📦 Checking database migration status..."
CURRENT_OUTPUT=$(alembic current 2>&1)
HEAD_OUTPUT=$(alembic heads 2>&1)
CURRENT_VERSIONS=$(printf '%s\n' "${CURRENT_OUTPUT}" | awk '/^[[:alnum:]_]+([[:space:]]+\(head\))?$/ { print $1 }')
HEAD_VERSIONS=$(printf '%s\n' "${HEAD_OUTPUT}" | awk '/^[[:alnum:]_]+[[:space:]]+\(head\)$/ { print $1 }')
CURRENT_COUNT=$(printf '%s\n' "${CURRENT_VERSIONS}" | grep -c . || true)
HEAD_COUNT=$(printf '%s\n' "${HEAD_VERSIONS}" | grep -c . || true)
CURRENT_VERSION=$(printf '%s\n' "${CURRENT_VERSIONS}" | head -n 1)
HEAD_VERSION=$(printf '%s\n' "${HEAD_VERSIONS}" | head -n 1)

if [ "${CURRENT_COUNT}" = "1" ] \
    && [ "${HEAD_COUNT}" = "1" ] \
    && [ "${CURRENT_VERSION}" = "${HEAD_VERSION}" ]; then
    echo "   ✅ Database is up to date (${CURRENT_VERSION})"
else
    echo "   ❌ Pending or ambiguous migrations: current=${CURRENT_VERSIONS:-unknown}, head=${HEAD_VERSIONS:-unknown}"
    echo "   Run the production deployment worker; the API will not start on an incompatible schema."
    exit 1
fi

# Start the application
echo "🎯 Starting FastAPI application..."
exec "$@"
