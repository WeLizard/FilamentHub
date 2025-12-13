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
    database_url = os.getenv("DATABASE_URL", "postgresql+asyncpg://filamenthub:filamenthub@postgres:5432/filamenthub")
    
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

# Run migrations with proper error handling
echo "📦 Running database migrations..."
echo "   Checking current migration version..."
CURRENT_VERSION=$(alembic current 2>&1 | grep -oP '^\K[0-9a-f]+' || echo "none")
echo "   Current version: ${CURRENT_VERSION}"

echo "   Applying migrations to head..."
if alembic upgrade head; then
    echo "✅ Migrations applied successfully!"
    NEW_VERSION=$(alembic current 2>&1 | grep -oP '^\K[0-9a-f]+' || echo "unknown")
    echo "   New version: ${NEW_VERSION}"
else
    MIGRATION_ERROR=$?
    echo "❌ Migration failed with exit code: ${MIGRATION_ERROR}"
    echo "   This might be due to:"
    echo "   - Already applied migrations"
    echo "   - Schema conflicts"
    echo "   - Database connection issues"
    echo "   Check the logs above for details."
    echo "   Attempting to continue anyway..."
    # Не останавливаем контейнер, но логируем ошибку
fi

# Admin creation is done manually by user
# Use: docker-compose -f docker-compose.prod.yml exec backend python create_admin_direct.py
echo "ℹ️  Migrations completed. Admin user should be created manually if needed."
echo "   To create admin, run:"
echo "   docker-compose -f docker-compose.prod.yml exec backend python create_admin_direct.py"

# Start the application
echo "🎯 Starting FastAPI application..."
exec "$@"

