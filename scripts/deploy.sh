#!/bin/bash
# =============================================================================
# FilamentHub Deploy Script v2.0
# =============================================================================
# Простой и надёжный деплой с backup'ами и проверкой здоровья
# Использование: cd ~/FilamentHub && bash scripts/deploy.sh
# =============================================================================

set -e  # Остановка при ошибке

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}🚀 FilamentHub Deploy${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

# Переходим в директорию проекта
cd "$(dirname "$0")/.." || exit 1
PROJECT_DIR=$(pwd)
SITE_HOST="${SITE_HOST:-filamenthub.ru}"
echo -e "${GREEN}📁 Директория:${NC} $PROJECT_DIR"

# -----------------------------------------------------------------------------
# 1. BACKUP базы данных (если контейнер запущен)
# -----------------------------------------------------------------------------
echo ""
echo -e "${YELLOW}📦 Шаг 1: Backup базы данных...${NC}"

BACKUP_DIR="${BACKUP_DIR:-$PROJECT_DIR/backups}"
BACKUP_KEY="${BACKUP_PUBLIC_KEY:-$PROJECT_DIR/backup-key.pub.asc}"
mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"

if docker ps --format '{{.Names}}' | grep -q "filamenthub_postgres_prod"; then
    BACKUP_FILE="$BACKUP_DIR/backup_$(date +%Y%m%d_%H%M%S).sql"
    echo "   Создаю backup в $BACKUP_FILE..."

    if docker exec filamenthub_postgres_prod pg_dump -U filamenthub filamenthub > "$BACKUP_FILE" 2>/dev/null; then
        gzip "$BACKUP_FILE"
        BACKUP_FILE="$BACKUP_FILE.gz"

        if [ -f "$BACKUP_KEY" ]; then
            if gpg --batch --yes --quiet --trust-model always \
                   --recipient-file "$BACKUP_KEY" \
                   --output "$BACKUP_FILE.gpg" --encrypt "$BACKUP_FILE" \
               && [ -s "$BACKUP_FILE.gpg" ]; then
                rm -f "$BACKUP_FILE"
                BACKUP_FILE="$BACKUP_FILE.gpg"
                echo -e "   ${GREEN}✅ Backup создан и зашифрован: $BACKUP_FILE${NC}"
            else
                rm -f "$BACKUP_FILE.gpg"
                echo -e "   ${RED}❌ Не удалось зашифровать backup. Оставлен незашифрованным: $BACKUP_FILE${NC}"
            fi
        else
            echo -e "   ${RED}❌ Ключ шифрования не найден: $BACKUP_KEY${NC}"
            echo -e "   ${RED}   Backup лежит в открытом виде: $BACKUP_FILE${NC}"
        fi

        ls -t "$BACKUP_DIR"/backup_*.sql.gz* 2>/dev/null | tail -n +6 | xargs -r rm -f
        echo "   Старые backup'ы очищены (оставлено последних 5)"
    else
        echo -e "   ${YELLOW}⚠️  Не удалось создать backup (продолжаем без него)${NC}"
    fi
else
    echo -e "   ${YELLOW}⚠️  PostgreSQL не запущен, пропускаю backup${NC}"
fi

# -----------------------------------------------------------------------------
# 2. Обновление кода из Git
# -----------------------------------------------------------------------------
echo ""
echo -e "${YELLOW}📥 Шаг 2: Обновление кода из Git...${NC}"

# Определяем ветку (main или master)
BRANCH="main"
if ! git show-ref --verify --quiet refs/remotes/origin/main; then
    BRANCH="master"
fi

# Получаем изменения (без submodule — OrcaSlicer не нужен на сервере)
git fetch --no-recurse-submodules origin "$BRANCH" || {
    echo -e "${RED}❌ Ошибка: не удалось получить изменения из Git${NC}"
    exit 1
}

# Показываем что изменится
CHANGES=$(git log HEAD..origin/$BRANCH --oneline 2>/dev/null || echo "")
if [ -n "$CHANGES" ]; then
    echo "   Новые коммиты:"
    echo "$CHANGES" | head -5 | sed 's/^/   - /'
    COMMIT_COUNT=$(echo "$CHANGES" | wc -l)
    if [ "$COMMIT_COUNT" -gt 5 ]; then
        echo "   ... и ещё $((COMMIT_COUNT - 5)) коммит(ов)"
    fi
else
    echo "   Новых коммитов нет"
fi

# Сбрасываем локальные изменения и обновляемся
echo "   Применяю изменения..."
git reset --hard origin/$BRANCH

echo -e "   ${GREEN}✅ Код обновлён${NC}"

# -----------------------------------------------------------------------------
# 3. Перезапуск контейнеров
# -----------------------------------------------------------------------------
echo ""
echo -e "${YELLOW}🔄 Шаг 3: Перезапуск контейнеров...${NC}"

# Используем docker compose (V2) вместо docker-compose (V1)
echo "   Пересобираю и запускаю контейнеры..."
COMPOSE_BAKE=false docker compose up -d --build

echo -e "   ${GREEN}✅ Контейнеры запущены${NC}"

# -----------------------------------------------------------------------------
# 3.6. Применение миграций БД (backup уже сделан в шаге 1 — это точка отката)
# -----------------------------------------------------------------------------
echo ""
echo -e "${YELLOW}🗄️  Шаг 3.6: Применение миграций БД...${NC}"

if docker ps --format '{{.Names}}' | grep -q "filamenthub_backend_prod"; then
    if docker exec filamenthub_backend_prod alembic upgrade head; then
        echo -e "   ${GREEN}✅ Миграции применены (или БД уже на head)${NC}"
    else
        echo -e "   ${RED}❌ Миграции НЕ применились — код задеплоен, но схема БД отстаёт.${NC}"
        LATEST_BACKUP=$(ls -t "$BACKUP_DIR"/backup_*.sql.gz 2>/dev/null | head -1)
        if [ -n "$LATEST_BACKUP" ]; then
            echo -e "   ${RED}   Откат БД из backup шага 1:${NC}"
            echo -e "   ${RED}   gunzip -c \"$LATEST_BACKUP\" | docker exec -i filamenthub_postgres_prod psql -U filamenthub filamenthub${NC}"
        fi
        exit 1
    fi
else
    echo -e "   ${YELLOW}⚠️  Контейнер backend не запущен, пропускаю миграции${NC}"
fi

# -----------------------------------------------------------------------------
# 3.5. Очистка старых Docker образов (оставляем текущий + предыдущий)
# -----------------------------------------------------------------------------
echo ""
echo -e "${YELLOW}🧹 Шаг 3.5: Очистка старых Docker образов...${NC}"

# Remove dangling images (untagged, not used by any container)
DANGLING=$(docker images -f "dangling=true" -q 2>/dev/null | wc -l)
if [ "$DANGLING" -gt 0 ]; then
    docker image prune -f > /dev/null 2>&1
    echo "   Удалено $DANGLING неиспользуемых образов"
fi

# Preserve recently used build layers (npm ci, pip installs, etc.) so unchanged
# dependencies are reused on the next deploy. Only stale cache is removed.
BUILD_CACHE_RETENTION="${BUILD_CACHE_RETENTION:-336h}"
docker builder prune -f --filter "until=${BUILD_CACHE_RETENTION}" > /dev/null 2>&1
echo "   Build cache моложе ${BUILD_CACHE_RETENTION} сохранён"

# Show disk usage
AVAIL=$(df -h / | awk 'NR==2{print $4}')
echo -e "   ${GREEN}✅ Очистка завершена. Свободно: ${AVAIL}${NC}"

# -----------------------------------------------------------------------------
# 4. Проверка здоровья
# -----------------------------------------------------------------------------
echo ""
echo -e "${YELLOW}🏥 Шаг 4: Проверка здоровья...${NC}"

# Ждём пока backend поднимется
echo "   Жду запуска backend (до 60 сек)..."
ATTEMPTS=0
MAX_ATTEMPTS=12

while [ $ATTEMPTS -lt $MAX_ATTEMPTS ]; do
    ATTEMPTS=$((ATTEMPTS + 1))

    # Проверяем что контейнер запущен и healthy через встроенный healthcheck
    HEALTH_STATUS=$(docker inspect --format='{{.State.Health.Status}}' filamenthub_backend_prod 2>/dev/null || echo "not_found")

    if [ "$HEALTH_STATUS" = "healthy" ]; then
        echo -e "   ${GREEN}✅ Backend работает!${NC}"
        break
    fi

    if [ $ATTEMPTS -eq $MAX_ATTEMPTS ]; then
        echo -e "   ${YELLOW}⚠️  Backend не отвечает (статус: $HEALTH_STATUS, проверь логи)${NC}"
    else
        echo "   Попытка $ATTEMPTS/$MAX_ATTEMPTS... (статус: $HEALTH_STATUS)"
        sleep 5
    fi
done

# Проверяем frontend через nginx: backend proxy, SPA index и статику
FRONTEND_OK=true

if curl -kfsS --max-time 10 -H "Host: $SITE_HOST" https://127.0.0.1/health > /dev/null 2>&1; then
    echo "   ✅ Nginx -> backend /health отвечает"
else
    echo -e "   ${YELLOW}⚠️  Nginx -> backend /health не отвечает${NC}"
    FRONTEND_OK=false
fi

if curl -kfsS --max-time 10 -H "Host: $SITE_HOST" https://127.0.0.1/ > /dev/null 2>&1; then
    echo "   ✅ SPA index отвечает по HTTPS"
else
    echo -e "   ${YELLOW}⚠️  SPA index не отвечает по HTTPS${NC}"
    FRONTEND_OK=false
fi

if curl -kfsS --max-time 10 -H "Host: $SITE_HOST" https://127.0.0.1/logo.svg > /dev/null 2>&1; then
    echo "   ✅ Статика frontend доступна"
else
    echo -e "   ${YELLOW}⚠️  Статика frontend не отвечает${NC}"
    FRONTEND_OK=false
fi

if [ "$FRONTEND_OK" = true ]; then
    echo -e "   ${GREEN}✅ Frontend работает!${NC}"
else
    echo -e "   ${YELLOW}⚠️  Frontend отвечает не полностью (проверь логи)${NC}"
fi

# -----------------------------------------------------------------------------
# 5. Итоги
# -----------------------------------------------------------------------------
echo ""
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}✅ Деплой завершён!${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo "Статус контейнеров:"
docker compose ps
echo ""
echo -e "${BLUE}💡 Полезные команды:${NC}"
echo "   docker compose logs -f          # Все логи"
echo "   docker compose logs -f backend  # Логи backend"
echo "   docker compose restart backend  # Перезапуск backend"
echo ""
