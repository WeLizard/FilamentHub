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

# Run migrations with proper error handling
echo "📦 Running database migrations..."

# Получаем текущую версию миграции из БД
echo "   Checking current migration version..."
CURRENT_OUTPUT=$(alembic current 2>&1)
CURRENT_VERSION=$(echo "${CURRENT_OUTPUT}" | grep -oP '^\K[0-9a-f]+' || echo "none")

# Получаем целевую версию (head)
HEAD_OUTPUT=$(alembic heads 2>&1)
HEAD_VERSION=$(echo "${HEAD_OUTPUT}" | grep -oP '^\K[0-9a-f]+' | head -n 1 || echo "unknown")

# Проверяем, есть ли база данных вообще (для новой установки)
if [ "${CURRENT_VERSION}" = "none" ]; then
    echo "   Database is empty, will apply all migrations from scratch"
    echo "   Target version: ${HEAD_VERSION}"
    NEEDS_MIGRATION=true
elif [ "${CURRENT_VERSION}" = "${HEAD_VERSION}" ]; then
    echo "   Current version: ${CURRENT_VERSION}"
    echo "   Target version: ${HEAD_VERSION}"
    echo "   ✅ Database is already up to date!"
    NEEDS_MIGRATION=false
else
    echo "   Current version: ${CURRENT_VERSION}"
    echo "   Target version: ${HEAD_VERSION}"
    echo "   ⬆️  Pending migrations detected, will upgrade..."
    NEEDS_MIGRATION=true
fi

# Применяем миграции только если нужно
if [ "${NEEDS_MIGRATION}" = "true" ]; then
    echo "   Applying migrations to head..."
    # Применяем миграции с обработкой множественных heads
    if alembic upgrade head 2>&1 | tee /tmp/migration.log; then
        # Получаем новую версию после применения
        NEW_OUTPUT=$(alembic current 2>&1)
        NEW_VERSION=$(echo "${NEW_OUTPUT}" | grep -oP '^\K[0-9a-f]+' || echo "unknown")
        
        if [ "${NEW_VERSION}" = "unknown" ]; then
            echo "   ⚠️  Warning: Could not determine migration version after upgrade"
            echo "   Check /tmp/migration.log for details"
        elif [ "${NEW_VERSION}" = "${HEAD_VERSION}" ]; then
            echo "   ✅ Migrations applied successfully!"
            echo "   New version: ${NEW_VERSION}"
            if [ "${CURRENT_VERSION}" != "none" ] && [ "${CURRENT_VERSION}" = "${NEW_VERSION}" ]; then
                echo "   ℹ️  Note: Version unchanged (may have been already applied)"
            fi
        else
            echo "   ⚠️  Warning: Migration version mismatch"
            echo "   Expected: ${HEAD_VERSION}, Got: ${NEW_VERSION}"
            echo "   Check /tmp/migration.log for details"
        fi
    else
        MIGRATION_ERROR=$?
        echo "   ❌ Migration failed with exit code: ${MIGRATION_ERROR}"
        echo "   Check /tmp/migration.log for details"
        echo "   Attempting to continue anyway..."
    fi
fi

# Admin creation is done manually by user
echo "ℹ️  Migrations completed. Admin user should be created manually if needed."
echo "   To create admin, run:"
echo "   docker-compose exec backend python create_admin_direct.py"

# Start the application
echo "🎯 Starting FastAPI application..."
exec "$@"

