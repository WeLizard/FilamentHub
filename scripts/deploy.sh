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
echo -e "${GREEN}📁 Директория:${NC} $PROJECT_DIR"

# -----------------------------------------------------------------------------
# 1. BACKUP базы данных (если контейнер запущен)
# -----------------------------------------------------------------------------
echo ""
echo -e "${YELLOW}📦 Шаг 1: Backup базы данных...${NC}"

BACKUP_DIR="$PROJECT_DIR/backend/uploads/database_dumps"
mkdir -p "$BACKUP_DIR"

if docker ps --format '{{.Names}}' | grep -q "filamenthub_postgres_prod"; then
    BACKUP_FILE="$BACKUP_DIR/backup_$(date +%Y%m%d_%H%M%S).sql"
    echo "   Создаю backup в $BACKUP_FILE..."
    
    if docker exec filamenthub_postgres_prod pg_dump -U filamenthub filamenthub > "$BACKUP_FILE" 2>/dev/null; then
        # Сжимаем backup
        gzip "$BACKUP_FILE"
        echo -e "   ${GREEN}✅ Backup создан: ${BACKUP_FILE}.gz${NC}"
        
        # Удаляем старые backup'ы (оставляем последние 5)
        ls -t "$BACKUP_DIR"/backup_*.sql.gz 2>/dev/null | tail -n +6 | xargs -r rm -f
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

# Получаем изменения
git fetch origin main 2>/dev/null || git fetch origin master 2>/dev/null || {
    echo -e "${RED}❌ Ошибка: не удалось получить изменения из Git${NC}"
    exit 1
}

# Показываем что изменится
CHANGES=$(git log HEAD..origin/main --oneline 2>/dev/null || git log HEAD..origin/master --oneline 2>/dev/null || echo "")
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
git reset --hard origin/main 2>/dev/null || git reset --hard origin/master

echo -e "   ${GREEN}✅ Код обновлён${NC}"

# -----------------------------------------------------------------------------
# 3. Перезапуск контейнеров
# -----------------------------------------------------------------------------
echo ""
echo -e "${YELLOW}🔄 Шаг 3: Перезапуск контейнеров...${NC}"

# Используем docker compose (V2) вместо docker-compose (V1)
echo "   Пересобираю и запускаю контейнеры..."
docker compose up -d --build

echo -e "   ${GREEN}✅ Контейнеры запущены${NC}"

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
    
    # Проверяем health endpoint
    if curl -sf http://localhost:8000/health > /dev/null 2>&1; then
        echo -e "   ${GREEN}✅ Backend работает!${NC}"
        break
    fi
    
    if [ $ATTEMPTS -eq $MAX_ATTEMPTS ]; then
        echo -e "   ${YELLOW}⚠️  Backend не отвечает на /health (возможно всё ок, проверь логи)${NC}"
    else
        echo "   Попытка $ATTEMPTS/$MAX_ATTEMPTS..."
        sleep 5
    fi
done

# Проверяем frontend
if curl -sf http://localhost:80 > /dev/null 2>&1 || curl -sf https://localhost:443 -k > /dev/null 2>&1; then
    echo -e "   ${GREEN}✅ Frontend работает!${NC}"
else
    echo -e "   ${YELLOW}⚠️  Frontend не отвечает (проверь логи)${NC}"
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
