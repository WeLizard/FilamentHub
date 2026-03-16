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

# Check migration status (informational only — migrations are applied via admin panel)
echo "📦 Checking database migration status..."
CURRENT_OUTPUT=$(alembic current 2>&1)
CURRENT_VERSION=$(echo "${CURRENT_OUTPUT}" | grep -oP '^\K[0-9a-f]+' || echo "none")
HEAD_OUTPUT=$(alembic heads 2>&1)
HEAD_VERSION=$(echo "${HEAD_OUTPUT}" | grep -oP '^\K[0-9a-f]+' | head -n 1 || echo "unknown")

if [ "${CURRENT_VERSION}" = "${HEAD_VERSION}" ]; then
    echo "   ✅ Database is up to date (${CURRENT_VERSION})"
else
    echo "   ⚠️  Pending migrations: current=${CURRENT_VERSION}, head=${HEAD_VERSION}"
    echo "   Apply via admin panel: Settings → Database → Migrations"
fi

# Start the application
echo "🎯 Starting FastAPI application..."
exec "$@"

